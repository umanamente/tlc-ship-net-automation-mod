-- The stock pointer provides the player's remappable Interact action, reach,
-- blocking world trace and hover selection. Query only the visible triangles.
local valid=require("shipnet.observer").valid
local M={}
M.__index=M
local PTR="/Script/Voyage.InteractiveDetectorPointerComponent"
local MATH="/Script/Engine.Default__KismetMathLibrary"
local HUD="/Game/UI/Game/HUD/BP_VoyageIngameHud.BP_VoyageIngameHud_C"
local BUILT="/Game/Mods/ShipNetAutomation/BP_Module_WinchAutomator.BP_Module_WinchAutomator_C"
local function same(a,b) return valid(a) and valid(b) and a:GetAddress()==b:GetAddress() end
local function unwrap(x) return x and type(x.get)=="function" and x:get() or x end
local function point(p) return {X=p.X,Y=p.Y,Z=p.Z} end
local BORE_RADIUS=9
local WIDGET_OVERLAY,NO_INTERACT=1,3 -- FVoyageInteractType

-- SocketView is itself an oversized stock BoxComponent. On a stand-alone
-- outlet the 20 cm hover sweep is convenient. On a cabinet it lets a plug
-- start through a perpendicular fascia. Change only the preview's interaction
-- query responses; never disconnect, unregister, or disable power simulation.
function M:_allowSocket(allow)
    if not self.socketShapes or self.socketAllowed==allow then return end
    for _,record in ipairs(self.socketShapes) do
        if valid(record.c) then
            for channel,response in pairs(record.responses) do
                record.c:SetCollisionResponseToChannel(channel,allow and response or 0)
            end
        end
    end
    self.socketAllowed=allow
end

function M:_enableInletWhenAimed()
    if not self.socketShapes then return end
    local pc,ptr=self.pc,self.pointer
    local camera=pc.PlayerCameraManager
    if not valid(camera) then self:_allowSocket(false);return end
    local eye=camera:GetCameraLocation()
    local origin=self.actor:K2_GetActorLocation()
    local dx,dy,dz=eye.X-origin.X,eye.Y-origin.Y,eye.Z-origin.Z
    if dx*dx+dy*dy+dz*dz>(ptr.MaxReach+100)^2 then self:_allowSocket(false);return end
    local maths=StaticFindObject(MATH)
    local frame=self.actor:GetTransform()
    local p=maths:InverseTransformLocation(frame,eye)
    local d=maths:InverseTransformDirection(frame,maths:GetForwardVector(camera:GetCameraRotation()))
    local face=self.socketFace
    local t, radial
    if self.basic then
        t=d.Y<-.001 and (face.Y-p.Y)/d.Y or -1
        radial=p.X+t*d.X-face.X
    else
        t=d.X>.001 and (face.X-p.X)/d.X or -1
        radial=p.Y+t*d.Y-face.Y
    end
    local z=p.Z+t*d.Z-face.Z
    self:_allowSocket(t>=0 and t<=ptr.MaxReach and radial*radial+z*z<=BORE_RADIUS^2)
end

function M:_mountSocket(power)
    if not power or not power.socket then return end
    local socket=StaticFindObject(power.socket)
    if not valid(socket) or not same(socket:GetOwner(),self.actor) then return end
    self.socketShapes={}
    local function remember(c)
        if not valid(c) or not same(c:GetOwner(),self.actor) then return end
        for _,r in ipairs(self.socketShapes) do if same(r.c,c) then return end end
        local entry={c=c,responses={}}
        for channel=9,14 do
            local response=c:GetCollisionResponseToChannel(channel)
            if response~=0 then entry.responses[channel]=response end
        end
        self.socketShapes[#self.socketShapes+1]=entry
    end
    remember(socket);remember(socket.SocketCollisionBox);remember(socket.mesh)
    local half=point(socket:GetUnscaledBoxExtent())
    self.originalSocketExtent=half
    socket:SetBoxExtent({X=math.min(half.X,BORE_RADIUS),Y=math.min(half.Y,BORE_RADIUS),Z=math.min(half.Z,6.5)},false)
    local inlet=self.geometry.anchors.inlet
    self.socketFace=power.renderedMeshFit and power.renderedMeshFit.matingSideBoundLocalCm
        or (self.basic and {X=inlet.X,Y=inlet.Y+3,Z=inlet.Z} or {X=inlet.X-6,Y=inlet.Y,Z=inlet.Z})
    self:_allowSocket(false)
end

function M:unmount()
    for _,h in ipairs(self.nativeHooks or {}) do pcall(UnregisterHook,table.unpack(h)) end
    self.nativeHooks,self.native,self.nextNativeCheck=nil,nil,nil
    if not self.basic and valid(self.containerAction) and self.containerAction.InteractType==NO_INTERACT then
        self.containerAction.InteractType=WIDGET_OVERLAY
    end
    self.containerAction=nil
    if self.timer and type(CancelDelayedAction)=="function" then pcall(CancelDelayedAction,self.timer) end
    if self.socketShapes then
        pcall(self._allowSocket,self,true)
        local socket=self.socketShapes[1] and self.socketShapes[1].c
        if valid(socket) and self.originalSocketExtent then pcall(function() socket:SetBoxExtent(self.originalSocketExtent,false) end) end
    end
    self.socketShapes,self.socketAllowed,self.originalSocketExtent,self.socketFace=nil,nil,nil,nil
    if self.mesh and self.parts then
        for _,name in pairs(self.parts) do
            local c=self.mesh[name]
            if valid(c) then pcall(function() c:SetCollisionEnabled(0) end) end
        end
    end
    self.timer,self.actor,self.mesh,self.pc,self.pointer=nil,nil,nil,nil,nil
    self.carrierMesh=nil
    self.keys,self.down,self.pulse,self.lastKeyRefresh=nil,nil,nil,nil
    self.action,self.parts,self.mapping,self.lastTarget,self.lastResult,self.actionTime=nil,nil,nil,nil,nil,nil
    self.detail,self.state=nil,"hidden"
end

function M:status()
    return {status=self.state,detail=self.detail,mapping=self.mapping,lastTarget=self.lastTarget,lastResult=self.lastResult,
        inletAimEnabled=self.socketAllowed}
end

function M:_player()
    if valid(self.pc) and valid(self.pointer) and same(self.pc.Pawn,self.pointer:GetOwner()) then return true end
    self.pc,self.pointer,self.keys,self.down=nil,nil,nil,nil
    local pc=FindFirstOf("VoyagePlayerController")
    if not valid(pc) or not pc:IsLocalController() or not valid(pc.Pawn) then return false end
    local pointer=pc.Pawn:GetComponentByClass(StaticFindObject(PTR))
    if not valid(pointer) then return false end
    self.pc,self.pointer=pc,pointer
    return true
end

function M:_keyState()
    local now=os.time()
    if now~=self.lastKeyRefresh or not self.keys then
        self.lastKeyRefresh=now
        local action=unwrap(self.pointer.InteractIndexInputActions[1])
        local library=StaticFindObject("/Script/Engine.Default__SubsystemBlueprintLibrary")
        local cls=StaticFindObject("/Script/EnhancedInput.EnhancedInputLocalPlayerSubsystem")
        local subsystem=library:GetLocalPlayerSubSystemFromPlayerController(self.pc,cls)
        local keys,names={},{}
        if valid(subsystem) and valid(action) then
            for _,p in ipairs(subsystem:QueryKeysMappedToAction(action)) do
                local s=unwrap(p).KeyName:ToString()
                names[#names+1]=s
                keys[#keys+1]={KeyName=FName(s,EFindName.FNAME_Find)}
            end
        end
        local mapping=table.concat(names," / ")
        if self.mapping~=mapping then self.down,self.pulse,self.actionTime=nil,nil,nil end
        self.keys,self.mapping=keys,mapping
        self.action=action
    end
    local held,pulse=false,false
    local playerInput=self.pc.PlayerInput
    if valid(playerInput) and valid(self.action) then
        local map=playerInput.ActionInstanceData
        if map and map:Contains(self.action) then
            local instance=unwrap(map:Find(self.action))
            local e=instance.TriggerEvent
            held=e==1 or e==2 or e==4
            local last=instance.LastTriggeredWorldTime
            pulse=last>0 and self.actionTime~=nil and last~=self.actionTime
            self.actionTime=last
        end
    end
    for _,key in ipairs(self.keys) do
        held=held or self.pc:IsInputKeyDown(key)
        pulse=pulse or self.pc:WasInputKeyJustPressed(key)
    end
    return held,pulse
end

local COLOR={R=0,G=0,B=0,A=0}
local function exact(pc,start,finish,channel)
    local hit={}
    local lib=StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    if not lib:LineTraceSingle(pc,start,finish,channel,true,{pc.Pawn},0,hit,true,COLOR,COLOR,0) then return end
    hit=hit.OutHit or hit
    return hit.Component:Get(),hit
end

function M:_surface(component)
    return valid(component) and same(component:GetOwner(),self.actor)
        and (self.parts[component:GetAddress()]~=nil or same(component,self.carrierMesh))
end

-- The native action provider can run before the pointer updates its hover
-- cache. Read the current projected aim for both publication and activation.
local function current_ray(pc,ptr)
    local start,direction={},{}
    if ptr:GetPointerLocation(start,direction) then
        start=start.OutLocation or start
        direction=direction.OutDirection or direction
        if type(start.X)=="number" and type(direction.X)=="number" then
            return start,{X=start.X+direction.X*ptr.MaxReach,Y=start.Y+direction.Y*ptr.MaxReach,
                Z=start.Z+direction.Z*ptr.MaxReach}
        end
    end
    local camera=pc.PlayerCameraManager
    if valid(camera) then
        start=camera:GetCameraLocation()
        direction=StaticFindObject(MATH):GetForwardVector(camera:GetCameraRotation())
        return start,{X=start.X+direction.X*ptr.MaxReach,Y=start.Y+direction.Y*ptr.MaxReach,
            Z=start.Z+direction.Z*ptr.MaxReach}
    end
end

function M:target(fresh)
    if not valid(self.actor) or not self.parts or not self:_player() then return end
    local pc,ptr=self.pc,self.pointer
    local focus=pc:GetPlayerFocusWidget()
    if not ptr.bAllowInteract or pc.bShowMouseCursor or (valid(focus) and not focus:IsA(HUD)) then return end
    if StaticFindObject("/Script/Engine.Default__GameplayStatics"):IsGamePaused(pc) then return end
    local start,finish
    if fresh then
        start,finish=current_ray(pc,ptr)
        if not start then return end
    else
        local sight=ptr:GetHoverResult()
        if not self:_surface(sight.Component:Get()) then return end
        start,finish=sight.TraceStart,sight.TraceEnd
    end
    -- The stock pointer can choose a nearby socket up to 20 cm off-axis.
    -- Reuse its projected sight line for genuine line (not sweep) traces.
    -- TraceTypeQuery3 is Interact on this game build; Query1 is Visibility.
    local hitComponent,hit=exact(pc,start,finish,2)
    if not self:_surface(hitComponent) then return end
    if type(hit.Distance)~="number" or hit.Distance<=0 or hit.Distance>ptr.MaxReach then return end
    local obstacle,wall=exact(pc,start,hit.ImpactPoint,0)
    if valid(obstacle) and not same(obstacle:GetOwner(),self.actor) and wall.Distance+.2<hit.Distance then return end
    local maths=StaticFindObject(MATH)
    local frame=self.actor:GetTransform()
    local p=point(maths:InverseTransformLocation(frame,hit.ImpactPoint))
    local n=point(maths:InverseTransformDirection(frame,hit.ImpactNormal))
    -- The socket is a distinct stock component. Its own cable interactions may
    -- target a different object channel. Reserve the inlet bore on the left.
    local inlet=self.geometry.anchors.inlet
    if n.X<-.3 and p.X<inlet.X+3 and (p.Y-inlet.Y)^2+(p.Z-inlet.Z)^2<9^2 then return end
    local s=self.geometry.fitGeometry.display
    local screen=n.Y>.75 and math.abs(p.Y-(s.lensY or s.Y))<1.5 and p.X>=s.minX and p.X<=s.maxX and p.Z>=s.minZ and p.Z<=s.maxZ
    if screen then return "screen",p end
    if not self.basic then return "storage",p end
end

function M:activate()
    local kind=self:target()
    if not kind then return false,"No reachable device surface" end
    self.lastTarget=kind
    local ok,reason=self.dispatch(kind,self.pc)
    self.lastResult=ok and "opened" or tostring(reason or "Unable to open")
    return ok,reason
end

function M:hint()
    if self.native then return end -- the native action provider owns the prompt
    if not valid(self.actor) or not self.mapping or self.mapping=="" then return end
    local kind=self:target()
    if kind then return {key=self.mapping,target=kind,label=kind=="screen" and "Winch settings" or "Open storage"} end
end

function M:_containerRouting(surface)
    local action=self.containerAction
    if not valid(action) or not self.pc or self.pc.bShowMouseCursor then return end
    local desired=not self.basic and surface==0 and WIDGET_OVERLAY or NO_INTERACT
    if action.InteractType~=desired then action.InteractType=desired end
end

function M:_nativeSurface(pawn)
    if not self:_player() or (valid(pawn) and not same(pawn,self.pc.Pawn)) then return 2 end
    local target=self:target(true)
    local surface=2 -- the cabinet has no action on cables, other objects, or obscured surfaces
    if target=="screen" then surface=1 elseif target=="storage" then surface=0 end
    -- A stock container also has an implicit WidgetOverlay interaction, in
    -- addition to the action supplied by its Blueprint. Only casing uses it.
    self:_containerRouting(surface)
    return surface
end

function M:_registerNative()
    if self.nativeHooks or os.time()<self.nextNativeCheck then return end
    self.nextNativeCheck=os.time()+2
    local hooks={}
    local function bind(member,fn)
        local path=(self.carrierClass or BUILT)..":"..member
        assert(valid(StaticFindObject(path)),"Missing native cabinet function "..member)
        local pre,post=RegisterHook(path,fn)
        hooks[#hooks+1]={path,pre,post}
    end
    local ok,why=pcall(function()
        bind("ResolveWinchSurface",function(ctx,character)
            local actor=ctx:get()
            if not same(actor,self.actor) then return end
            local success,kind=pcall(self._nativeSurface,self,unwrap(character))
            actor.WinchAimSurface=success and kind or 2
            if not success then self.detail=tostring(kind) end
        end)
        bind("WinchControlTriggered",function(ctx,action)
            if not same(ctx:get(),self.actor) then return end
            local success,err=pcall(function()
                local input=unwrap(action)
                if not input or not self:_player() or not same(input.Controller,self.pc) or self:_nativeSurface()~=1 then return end
                self.lastTarget="screen"
                local opened,reason=self.dispatch("screen",self.pc)
                self.lastResult=opened and "opened" or tostring(reason)
            end)
            if not success then self.detail=tostring(err) end
        end)
    end)
    if not ok then
        for _,h in ipairs(hooks) do pcall(UnregisterHook,table.unpack(h)) end
        self.detail=tostring(why)
        return
    end
    self.nativeHooks,self.detail=hooks,nil
end

function M:poll()
    if not valid(self.actor) or not self:_player() then return end
    self:_enableInletWhenAimed()
    if self.native then
        self:_registerNative()
        if valid(self.containerAction) and not self.pc.bShowMouseCursor then
            local hovered=self.pointer:GetHoverResult().Component:Get()
            if valid(hovered) and same(hovered:GetOwner(),self.actor) then self:_nativeSurface()
            else self:_containerRouting(2) end
        end
        return
    end
    local held,pulse=self:_keyState()
    local pressed=self.down==false and (held or (pulse and not self.pulse))
    self.down,self.pulse=held,pulse
    if pressed then self:activate() end
end

function M:mount(actor,mesh,geometry,dispatch,power,carrierMesh,built,variant)
    self:unmount()
    self.actor,self.mesh,self.geometry,self.dispatch=actor,mesh,geometry,dispatch
    -- The native fabricated mesh keeps its collision for stock tools. A trace
    -- on an overlapping v04 face may select either it or the animated surface.
    self.carrierMesh=carrierMesh
    self.basic,self.carrierClass=variant and variant.manualUnload,variant and variant.carrier
    self.native,self.nextNativeCheck=built==true,0
    self.parts={}
    local id=FName("Interactive",EFindName.FNAME_Find)
    -- The stock LED plane is visual only. The recessed track is part of the body.
    for _,name in ipairs(self.basic and {"body","drive"} or {"body","hatch","drive"}) do
        local c=mesh[name]
        assert(valid(c),"Missing device part "..name)
        self.parts[c:GetAddress()]=name
        c:SetCollisionProfileName(id,true)
        c:SetCollisionEnabled(1) -- query only
        c:SetCollisionResponseToChannel(3,2) -- native cable acquisition must respect the opaque casing
        c:SetGenerateOverlapEvents(false)
    end
    self:_mountSocket(power)
    if self.native then
        if not self.basic then
            local action=actor.InteractiveObject
            if valid(action) and same(action:GetOwner(),actor) and action.InteractType==WIDGET_OVERLAY then
                self.containerAction=action
                action.InteractType=NO_INTERACT
            end
            if actor.InteractEnabled==false then actor:SetInteractionEnabled(true) end
        end
        self:_registerNative()
    end
    self.state="ready"
    self.timer=LoopInGameThreadWithDelay(15,function()
        local ok,why=pcall(self.poll,self)
        if not ok then self.detail=tostring(why) end
    end)
    return self:status()
end

return {new=function() return setmetatable({state="hidden"},M) end}
