"""Read one Voyage save and express the saved player origin in the barge's frame."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import re
import struct


MARKER = bytes.fromhex("c1832a9e22222222")
U32 = struct.Struct("<I")
PACKED = struct.Struct("<3d6e")
TRIPLE = struct.Struct("<3d")


def fstring(text):
    value = text.encode("ascii") + b"\0"
    return U32.pack(len(value)) + value


def struct_tag(field, kind, package):
    return (fstring(field) + fstring("StructProperty") + U32.pack(1) + fstring(kind)
            + U32.pack(1) + fstring(package) + U32.pack(0))


ACTOR_NAME = fstring("ActorName") + fstring("NameProperty") + U32.pack(0)
TEMPLATE = fstring("ActorTemplate") + fstring("SoftObjectProperty")
TRANSFORM = struct_tag("Transform", "VoyagePackedTransform", "/Script/Voyage") + U32.pack(36) + b"\x08"
PLAYER = struct_tag("PlayerData", "PersistentPlayerData", "/Script/Voyage")


def decompress_save(path, dll):
    data = path.read_bytes()
    library = ctypes.CDLL(str(dll.resolve(strict=True)))
    decode = library.OodleLZ_Decompress
    ptr, size, integer = ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int
    decode.argtypes = [ptr, size, ptr, size, integer, integer, integer, ptr, size, ptr, ptr, ptr, size, integer]
    decode.restype = size
    raw = bytearray()
    pos = 0
    expected = None
    while pos < len(data):
        if not data.startswith(MARKER, pos) or pos + 49 > len(data) or data[pos + 16] != 2:
            raise ValueError(f"Unsupported compressed block at byte {pos}")
        limit, = struct.unpack_from("<Q", data, pos + 8)
        packed, unpacked, p2, u2 = struct.unpack_from("<4Q", data, pos + 17)
        start, end = pos + 49, pos + 49 + packed
        if (packed != p2 or unpacked != u2 or not 0 < unpacked <= limit <= 16 * 1024 * 1024
                or not packed or end > len(data) or (expected is not None and len(raw) + unpacked > expected)):
            raise ValueError(f"Invalid compressed block sizes at byte {pos}")
        buf = ctypes.create_string_buffer(unpacked)
        if decode(data[start:end], packed, buf, unpacked, 1, 0, 0, None, 0, None, None, None, 0, 3) != unpacked:
            raise ValueError(f"Oodle could not read block at byte {pos}")
        raw.extend(buf.raw)
        if expected is None:
            if raw[4:8] != b"GVAS":
                raise ValueError("Missing length-prefixed GVAS header")
            expected = 4 + U32.unpack_from(raw)[0]
        pos = end
    if expected is None or len(raw) != expected:
        raise ValueError("GVAS payload length mismatch")
    return raw


def unique(values, label):
    if len(values) != 1:
        raise ValueError(f"Expected exactly one {label}, found {len(values)}")
    return values[0]


def bounded_values(fmt, raw, position):
    values = fmt.unpack_from(raw, position)
    if not all(math.isfinite(x) for x in values):
        raise ValueError(f"Nonfinite coordinates at byte {position}")
    return values


def actor_transforms(raw):
    # Match the field name, type, serializer sizes and following property. A name in
    # a saved reference or component list does not identify a top-level actor.
    pattern = re.compile(re.escape(ACTOR_NAME) + rb"(.{4})\x00(.{4})"
                         rb"(BP_(?:Boat_Barge_C_?\d+(?:LevelInstanceBP_Module_Fishing_C_\d+)?"
                         rb"|FirstPersonCharacter_New_C_?\d+))\x00" + re.escape(TEMPLATE), re.DOTALL)
    results = {}
    for match in pattern.finditer(raw):
        name = match[3].decode("ascii")
        length = len(match[3]) + 1
        if U32.unpack(match[1])[0] != length + 4 or U32.unpack(match[2])[0] != length:
            raise ValueError(f"Invalid serialized name for {name}")
        end = raw.find(ACTOR_NAME, match.end())
        if end == -1:
            end = len(raw)
        tag = raw.find(TRANSFORM, match.end(), end)
        following = tag + len(TRANSFORM) + PACKED.size
        if tag == -1 or not raw.startswith(fstring("ComponentTransforms"), following):
            raise ValueError(f"Missing top-level packed transform for {name}")
        if name in results:
            raise ValueError(f"Duplicate actor {name}")
        results[name] = bounded_values(PACKED, raw, tag + len(TRANSFORM))
    return results


def player_fields(raw):
    index = unique([m.end() for m in re.finditer(re.escape(PLAYER), raw)], "PersistentPlayerData")
    length = U32.unpack_from(raw, index)[0]
    start, end = index + 5, index + 5 + length
    if raw[index + 4] != 0 or end > len(raw):
        raise ValueError("Invalid PersistentPlayerData payload")

    def read(name, kind):
        tag = struct_tag(name, kind, "/Script/CoreUObject") + U32.pack(24) + b"\x08"
        pos = raw.find(tag, start, end)
        if pos < 0 or pos + len(tag) + TRIPLE.size > end or raw.find(tag, pos + len(tag), end) != -1:
            raise ValueError(f"Missing or ambiguous PlayerData.{name}")
        return bounded_values(TRIPLE, raw, pos + len(tag))

    return read("LastLocation", "Vector"), read("ControllerRotation", "Rotator")


def basis(rotation):
    pitch, yaw, roll = map(math.radians, rotation)
    sp, cp = math.sin(pitch), math.cos(pitch)
    sy, cy = math.sin(yaw), math.cos(yaw)
    sr, cr = math.sin(roll), math.cos(roll)
    # Unreal FRotationMatrix has local forward, right and up as its rows.
    return ((cp*cy, cp*sy, sp), (sr*sp*cy-cr*sy, sr*sp*sy+cr*cy, -sr*cp),
            (-cr*sp*cy-sr*sy, sr*cy-cr*sp*sy, cr*cp))


def measure(raw):
    actors = actor_transforms(raw)
    ship = unique([n for n in actors if re.fullmatch(r"BP_Boat_Barge_C_?\d+", n)], "barge actor")
    net = unique([n for n in actors if n.startswith(ship + "LevelInstanceBP_Module_Fishing_C_")],
                 f"stock winch belonging to {ship}")
    xyz, rotation = player_fields(raw)
    hull = actors[ship]
    if any(abs(scale) < 1e-8 for scale in hull[6:]):
        raise ValueError("Ship transform has a zero scale axis")
    axes = basis(hull[3:6])

    def rotate_to_hull(v):
        return tuple(sum(a*b for a, b in zip(axis, v)) for axis in axes)

    def point_in_hull(v):
        delta = [a-b for a, b in zip(v, hull[:3])]
        return tuple(x/s for x, s in zip(rotate_to_hull(delta), hull[6:]))

    def vector(v):
        return dict(zip("XYZ", (round(x, 6) for x in v)))

    characters = [n for n in actors if n.startswith("BP_FirstPersonCharacter_New_C")]
    crosscheck = {"status": "missing" if not characters else "ambiguous", "actors": characters}
    if len(characters) == 1:
        offset = math.dist(xyz, actors[characters[0]][:3])
        crosscheck.update(status="matched" if offset <= 0.1 else "different", distanceCm=round(offset, 6))
    return {"measurement": "saved_player_origin", "ship": ship, "winch": net,
            "playerOriginShipLocalCm": vector(point_in_hull(xyz)),
            "viewDirectionShipLocal": vector(rotate_to_hull(basis(rotation)[0])),
            "winchOriginShipLocalCm": vector(point_in_hull(actors[net][:3])),
            "playerToWinchDistanceCm": round(math.dist(xyz, actors[net][:3]), 6),
            "characterOriginCheck": crosscheck}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path, help="saved .sav slot to read")
    parser.add_argument("--oodle", required=True, type=Path, help="local 64-bit Oodle decoder DLL")
    args = parser.parse_args()
    try:
        report = measure(decompress_save(args.save, args.oodle))
    except (OSError, ValueError, IndexError, struct.error, AttributeError) as err:
        parser.exit(1, f"Could not measure this save: {err}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
