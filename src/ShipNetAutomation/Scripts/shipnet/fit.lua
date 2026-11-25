-- Transient, game-thread fitting of the rail controller. Only our spawned actor is modified.
local observer = require("shipnet.observer")
local survey = require("shipnet.survey")
local model = require("shipnet.model")
local variants = require("shipnet.variants")
local power = require("shipnet.fit_power")
local interaction = require("shipnet.interaction")
local Fit = {}
Fit.__index = Fit
local valid = observer.valid
local MATH = "/Script/Engine.Default__KismetMathLibrary"
local BARGE = "/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C"
local NET = "/Game/Blueprints/Modules/Utility/Boat/BP_Module_Fishing.BP_Module_Fishing_C"
local BUILT = variants.advanced.carrier
local SAVED_SWITCH = {X=22, Y=-291, Z=187}
local SAVED_WINCH = {X=-1968, Y=793.5, Z=-118}
local CABINET_ORIGIN = {X=147.779,Y=-189.824,Z=126.859}
local AXES = {"X", "Y", "Z", "Yaw"}
local CARGO_WARNING_MARGIN_KG = 2

local function opt(fn)
    local ok, result = pcall(fn)
    if ok then return result end
end

local function same(a,b)
    return valid(a) and valid(b) and a:GetAddress()==b:GetAddress()
end

local function ref(ob)
    if not valid(ob) then return end
    local name = ob:GetFullName()
    return {path=assert(name:match("^[^ ]+ (/.+)$"), "invalid object path"), address=ob:GetAddress()}
end

local function resolve(id)
    if not id then return end
    local obj = StaticFindObject(id.path)
    if valid(obj) and obj:GetAddress() == id.address then return obj end
end

local function finite(n)
    return type(n)=="number" and n==n and math.abs(n)<math.huge
end

local function vec(v)
    return opt(function()
        if finite(v.X) and finite(v.Y) and finite(v.Z) then return {X=v.X,Y=v.Y,Z=v.Z} end
    end)
end

local function offsets(values)
    local result={}
    values=values or {}
    for _,axis in ipairs(AXES) do
        local n=values[axis]
        if n==nil then n=0 end
        assert(finite(n), "invalid " .. axis .. " adjustment")
        result[axis]=n
    end
    return result
end

local function child_attachment(net,key,alias)
    local c=opt(function() return net[key] end)
    if not valid(c) then c=opt(function() return net[alias] end) end
    if valid(c) and same(c:GetOwner(),net) then return c end
end

local function switch_anchor(net)
    local attachment=child_attachment(net,"SwitchChildActor","Switch")
    if not attachment then return end
    local actor=opt(function() return attachment.ChildActor end)
    local pivot=valid(actor) and opt(function() return actor.Pivot end)
    if valid(pivot) and same(pivot:GetOwner(),actor) then return pivot,"switch_pivot_component" end
    return attachment,"switch_child_origin"
end

local function choose_target(self)
    local measured=survey.capture()
    self.discovery={status=measured.status,detail=measured.detail,coordinateFrame=measured.coordinateFrame}
    if not measured.ship then return nil,measured.status end
    local ship=StaticFindObject(measured.ship:match("^[^ ]+ (/.+)$"))
    if not valid(ship) or not ship:IsA(BARGE) then return nil,"no_ship" end
    local net=measured.net and StaticFindObject(measured.net:match("^[^ ]+ (/.+)$"))
    if valid(net) and net:IsA(NET) and (measured.coordinateFrame=="same_world" or measured.coordinateFrame=="ship_loaded_level") then
        return {mount=net,ship=ship,net=net,mode="live_winch"}
    end
    if measured.status=="no_net" or measured.status=="unverified_net" or measured.status=="frame_unverified" then
        local net_count=0
        for _,candidate in ipairs(measured.candidates or {}) do
            if candidate.role=="winch" then net_count=net_count+1 end
        end
        if net_count<=1 then return {mount=ship, ship=ship, mode="saved_barge_reference"} end
    end
    return nil,measured.status
end

local function compute_base(target)
    local world_point,source
    if target.net then
        local c
        c,source=switch_anchor(target.net)
        if c then world_point=opt(function() return c:K2_GetComponentLocation() end) end
    end
    local pivot=world_point and opt(function()
        local mathlib=StaticFindObject(MATH)
        return vec(mathlib:InverseTransformLocation(target.mount:GetTransform(),world_point))
    end)
    if pivot then return pivot,source end
    local origin=target.net and {X=0,Y=0,Z=0} or SAVED_WINCH
    return {X=origin.X+SAVED_SWITCH.X,Y=origin.Y+SAVED_SWITCH.Y,Z=origin.Z+SAVED_SWITCH.Z},"saved_switch_actor_origin"
end

-- The inboard-facing fascia is +Y in UE; the coupling points aft along -X of the reference Barge.
-- Adjust yaw around the coupling rather than sweeping its end away from the spindle.
local function placement(base,offset)
    local tip=model.anchors.coupling
    local yaw=180+offset.Yaw
    local angle=math.rad(yaw)
    return {X=base.X-tip.X*math.cos(angle)+tip.Y*math.sin(angle)+offset.X,
        Y=base.Y-tip.X*math.sin(angle)-tip.Y*math.cos(angle)+offset.Y,
        Z=base.Z-tip.Z+offset.Z}, {Pitch=0,Yaw=yaw,Roll=0}
end

local function set_placement(self,actor,value)
    local point,rot=placement(self.base,value)
    actor:K2_GetRootComponent():K2_SetRelativeLocationAndRotation(point,rot,false,{},true)
    self.offset=value
    self.placement={locationCm=point,rotationDeg=rot,frame=self.mountRef.path}
end

-- Measured cabinet origin in the winch frame on the reference barge (see housing_relief).
-- The player-facing fit calibration belongs only to the disposable fitting model.
local function built_mount(ship,net)
    if not valid(ship) or not ship:IsA(BARGE) or not valid(net) or not net:IsA(NET) then return end
    return {X=CABINET_ORIGIN.X,Y=CABINET_ORIGIN.Y,Z=CABINET_ORIGIN.Z},{Pitch=0,Yaw=180,Roll=0}
end

local function snapshot(self,status,detail)
    local actor=resolve(self.actorRef)
    local net=resolve(self.netRef)
    local visible=valid(actor)
    local p=self.powerState
    if visible and (self.powerAttempted or (self.built and p and p.socket)) then
        p=opt(function() return self.power:inspect(actor) end) or p
    end
    return {status=status or (visible and "shown" or "hidden"),detail=detail,visible=visible,
        stockFullyRaised=opt(function() return net and net.FullyRaised end),
        stockNetDropped=opt(function() return net and net.NetDropped end),
        offset=offsets(self.offset),hatchDegrees=self.hatchDegrees,driveDegrees=self.driveDegrees,
        pose={hatchDegrees=self.hatchDegrees,driveDegrees=self.driveDegrees},power=p,interaction=self.interaction:status(),
        visualMethod=self.mesh and "procedural_blender_mesh" or nil,
        mesh=self.mesh and {triangles=self.mesh.triangles,vertices=self.mesh.vertices,sections=self.mesh.sections,
            lod=self.mesh.lod,screenFraction=self.mesh.screenFraction,lodError=self.mesh.lodError,
            lod1Triangles=self.mesh.far and self.mesh.far.ok and self.mesh.far.triangles+(self.mesh.sharedTriangles or 0) or nil,
            lod1Sections=self.mesh.far and self.mesh.far.ok and self.mesh.far.sections+(self.mesh.sharedSections or 0) or nil,
            lod1Palette=self.mesh.far and self.mesh.far.palette~=nil,lod1PaletteError=self.mesh.far and self.mesh.far.paletteError,
            labelError=self.mesh.labelError, lod1LabelError=self.mesh.far and self.mesh.far.labelError,
            materialStatus=self.mesh.materialStatus, crt=self.mesh.screenMaterial~=nil,
            playerBoxMeter=self.mesh.stockMeter, screenError=self.mesh.screenError, meterError=self.mesh.meterError,
            meterAlarmError=self.mesh.meterAlarmError, meterSweepError=self.mesh.meterSweepError} or nil,
        placement=self.placement,placementMode=self.mode,pivotSource=self.pivotSource,discovery=self.discovery,
        actor=self.actorRef and self.actorRef.path,winch=self.netRef and self.netRef.path}
end

local function forget(self)
    self.interaction:unmount()
    self.actorRef,self.mountRef,self.netRef,self.shipRef,self.worldRef=nil,nil,nil,nil,nil
    self.mesh,self.base,self.mode,self.pivotSource,self.placement=nil,nil,nil,nil,nil
    self.variant,self.lastBeaconError,self.lodPlayer=nil,nil,nil
    self.hatchDegrees,self.driveDegrees,self.powerState,self.powerAttempted=0,0,nil,false
    self.nextWorldCheck,self.nextPowerCheck=0,0
    self.lastFill,self.lastFillAlarm,self.lastFillUnloading,self.lastFillUpdate=nil,nil,nil,nil
    self.power:reset()
end

local function build_model(self, actor, root)
    self.mesh=model.build(actor,root,self.variant==variants.basic,self.built)
    assert(self.mesh.ok,self.mesh.error or "Could not build controller geometry")
    if self.handlers and self.handlers.log then
        if self.mesh.screenError then self.handlers.log("CRT screen: "..self.mesh.screenError) end
        if self.mesh.meterError then self.handlers.log("Cargo LED meter: "..self.mesh.meterError) end
        if self.mesh.labelError then self.handlers.log("Printed labels: "..self.mesh.labelError) end
    end
end

local function guard(self,actor,reason)
    if not self.powerAttempted then return end
    local ok,read=pcall(self.power.before_remove,self.power,actor,reason)
    if ok and read and read.allowed then return end
    local result=snapshot(self,"cable_guard","Detach the cable in game before changing the mounted preview.")
    result.power=result.power or {}
    result.power.guard=ok and read or {allowed=false,status="connection_unknown",detail=tostring(read)}
    return result
end

function Fit:status()
    return snapshot(self)
end

function Fit:hide(reason)
    local actor=resolve(self.actorRef)
    if self.built then
        if self.screen then self.screen:destroy();self.screen=nil end
        self.screenRetry,self.screenError=nil,nil
        if self.cycle then self.cycle:reset(); self.cycle=nil end
        self.interaction:unmount()
        model.clear(self.mesh)
        for _,part in ipairs(self.stockVisuals) do
            if valid(part.component) then
                if part.collision then pcall(function() part.component:SetCollisionEnabled(part.collision) end) end
                pcall(function() part.component:SetVisibility(part.visible,false) end)
            end
        end
        self.built,self.stockVisuals,self.storage=nil,nil,nil
    elseif valid(actor) then
        if reason~="map_change" and reason~="mod_unload" then
            local blocked=guard(self,actor,reason or "user")
            if blocked then return blocked end
        end
        local ok,err=pcall(function() actor:K2_DestroyActor() end)
        if not ok then return snapshot(self,"error","Cannot remove preview: " .. tostring(err)) end
    end
    forget(self)
    return snapshot(self,"hidden")
end

local function replace_tags(tags,names)
    tags:Empty()
    for i,name in ipairs(names) do tags[i]=name end
end

local function protect_mount(actor)
    -- Voyage saves the tag array with each actor. Fabrication can also add
    -- Detachable, which the native grab command checks independently of NoGrab.
    local detachable=FName("Detachable",EFindName.FNAME_Find)
    local noGrab=FName("NoGrab",EFindName.FNAME_Find)
    local tags=actor.Tags
    local original,kept={},{}
    local hasNoGrab=false
    for i=1,tags:GetArrayNum() do
        local name=tags[i]
        original[i]=name
        if name~=detachable and not (name==noGrab and hasNoGrab) then kept[#kept+1]=name end
        if name==noGrab then hasNoGrab=true end
    end
    if hasNoGrab and #kept==#original then return end
    if not hasNoGrab then kept[#kept+1]=noGrab end
    local ok,why=pcall(function()
        replace_tags(tags,kept)
        assert(tags:GetArrayNum()==#kept and actor:ActorHasTag(noGrab) and not actor:ActorHasTag(detachable),
            "Could not protect the mounted controller from hand grabs")
    end)
    if not ok then
        replace_tags(tags,original)
        error(why,0)
    end
end

-- Only a finished, attached native object may receive the cabinet. All generated
-- surfaces are owned by it, so traces retain the fabricated actor as their target.
function Fit:bindBuilt(actor,ship,net)
    local bindingStarted=false
    local ok,why=pcall(function()
        assert(built_mount(ship,net),"Winch or barge unavailable")
        local kind=variants.forActor(actor)
        assert(kind and not actor:HasAnyFlags(0x30),"Wrong constructed actor")
        local parent=actor:GetAttachParentActor()
        assert(same(parent,ship) or same(parent,net),"Controller is not attached to the selected mount")
        local sub=StaticFindObject("/Script/Voyage.Default__VoyagePersistentSubsystem"):GetPersistentSubsystem(ship:GetWorld())
        assert(valid(sub) and sub:IsPersistentActor(actor),"Waiting for completed construction")
        protect_mount(actor)
        if self.built and same(resolve(self.actorRef),actor) and same(resolve(self.shipRef),ship)
            and same(resolve(self.netRef),net) then return end
        assert(self.built or not self.actorRef,"A fit preview already owns this runtime")
        if kind==variants.basic then require("shipnet.basic_saved_state").restore(actor,sub) end
        self:hide("map_change")
        bindingStarted=true
        self.built,self.stockVisuals,self.mode,self.variant=true,{},"fabricated",kind
        self.actorRef,self.mountRef,self.netRef,self.shipRef,self.worldRef=ref(actor),ref(parent),ref(net),ref(ship),ref(ship:GetWorld())
        if not kind.manualUnload then self.storage=require("shipnet.device_storage").forCarrier(actor,sub) end
        self.cycle=require("shipnet.automation").new(self.handlers and self.handlers.log,kind.manualUnload)
        build_model(self,actor,actor:K2_GetRootComponent())
        local visuals=kind==variants.basic and {"StaticMesh"}
            or {"StaticMesh","PlayerBox_Lid","LeftIconPlane","RightIconPlane","ResourceMeter","TextRender","VoyageContainerTextWidget"}
        for _,key in ipairs(visuals) do
            local part=opt(function() return actor[key] end)
            if valid(part) and same(part:GetOwner(),actor) then
                local original={component=part,visible=part:IsVisible()}
                self.stockVisuals[#self.stockVisuals+1]=original
                -- The carrier mesh supplies the tool and deck collision. The old box
                -- labels and trim can still intercept traces when merely invisible.
                if key~="StaticMesh" then
                    local collision=part:GetCollisionEnabled()
                    if collision~=0 then
                        original.collision=collision
                        part:SetCollisionEnabled(0)
                    end
                end
                part:SetVisibility(false,false)
            end
        end
        self.powerState=self.power:bindBuilt(actor,self.variant)
        self:_bindInteraction(actor)
    end)
    if not ok then
        if bindingStarted then self:hide("map_change") end
        return snapshot(self,"error",tostring(why))
    end
    return snapshot(self)
end

local function create(self,target,value)
    self.mode=target.mode
    self.base,self.pivotSource=compute_base(target)
    self.mountRef,self.netRef,self.shipRef,self.worldRef=ref(target.mount),ref(target.net),ref(target.ship),ref(target.ship:GetWorld())
    local parent=target.mount:K2_GetRootComponent()
    assert(valid(parent),"Winch/ship attachment root unavailable")
    local world=target.mount:GetWorld()
    local class=StaticFindObject("/Script/Engine.StaticMeshActor")
    assert(valid(world) and valid(class),"World or StaticMeshActor unavailable")
    -- Pinned UE4SS UWorld:SpawnActor explicitly rejects reflected UScriptStruct wrappers.
    -- Attachment snaps to the parent just below, so the initial rotation can be identity.
    local spawnPoint=assert(vec(target.mount:K2_GetActorLocation()),"Mount world location unavailable")
    local actor=world:SpawnActor(class,spawnPoint,{Pitch=0,Yaw=0,Roll=0})
    assert(valid(actor),"Could not spawn transient preview")
    self.actorRef=ref(actor)
    local comp=actor:K2_GetRootComponent()
    assert(valid(comp),"Preview has no root")
    comp:SetMobility(2)
    comp:SetCollisionEnabled(0)
    local noSocket=FName("None",EFindName.FNAME_Find)
    assert(actor:K2_AttachToComponent(parent,noSocket,2,2,2,false),"Engine rejected attachment to the selected mount")
    set_placement(self,actor,value)
    build_model(self,actor,comp)
    self.powerAttempted=true
    local ok,result=pcall(self.power.mount,self.power,actor)
    self.powerState=ok and result or {status="error",detail=tostring(result)}
    self:_bindInteraction(actor)
end

function Fit:_bindInteraction(actor)
    if not self.handlers then return end
    local geometry=self.variant and self.variant.geometry or model
    local ok,why=pcall(self.interaction.mount,self.interaction,actor,self.mesh,geometry,function(kind,pc)
        if kind=="screen" then return self.handlers.screen(pc) end
        if self.handlers.storage then return self.handlers.storage(pc,actor,resolve(self.shipRef)) end
        return self:openStorage(pc)
    end,self.powerState,self.built and opt(function() return actor.StaticMesh end) or nil,self.built,self.variant)
    if not ok then
        self.interaction:unmount()
        self.interaction.state,self.interaction.detail="unavailable",tostring(why)
        if self.handlers.log then self.handlers.log("Device interaction: "..tostring(why)) end
    end
end

function Fit:setInteractionHandlers(handlers)
    self.handlers=handlers
    if not handlers then self.interaction:unmount();return end
    local actor=resolve(self.actorRef)
    if valid(actor) then self:_bindInteraction(actor) end
end

function Fit:interactionStatus()
    return self.interaction:status()
end

function Fit:interactionHint()
    return opt(function() return self.interaction:hint() end)
end

function Fit:setFill(fraction, alarm, unloading)
    if not self.mesh then return false,"Device is hidden" end
    unloading = unloading == true
    if self.lastFill==fraction and self.lastFillAlarm==alarm and self.lastFillUnloading==unloading then return true end
    local previousAlarmError, previousSweepError = self.mesh.meterAlarmError, self.mesh.meterSweepError
    local ok,why=model.setFill(self.mesh,fraction,alarm,unloading)
    if ok then
        self.lastFill,self.lastFillAlarm,self.lastFillUnloading=fraction,alarm,unloading
        local log = self.handlers and self.handlers.log
        if log and self.mesh.meterAlarmError and self.mesh.meterAlarmError~=previousAlarmError then
            log("Cargo LED alarm: "..self.mesh.meterAlarmError)
        end
        if log and self.mesh.meterSweepError and self.mesh.meterSweepError~=previousSweepError then
            log("Cargo LED sweep: "..self.mesh.meterSweepError)
        end
    end
    return ok,why
end

function Fit:_storage()
    if not self.storage then self.storage=require("shipnet.device_storage").new() end
    return self.storage
end

local function attached_device(self,actor)
    return valid(actor) and (not self.built or same(opt(function() return actor:GetAttachParentActor() end),resolve(self.mountRef)))
end

function Fit:openStorage(pc)
    if self.variant==variants.basic then return false,"Use the stock catch drawer" end
    local actor,ship=resolve(self.actorRef),resolve(self.shipRef)
    if not attached_device(self,actor) or not valid(ship) then return false,"Device is unavailable" end
    local ok,opened,result=pcall(function() return self:_storage():open(pc,actor,ship) end)
    if not ok then return false,tostring(opened) end
    return opened,opened and "Storage open" or result
end

local function cargo_alarm(actor, net, status)
    local storage=status.storage
    if finite(storage.capacityKg) and storage.capacityKg>0 and finite(storage.weightKg)
        and storage.weightKg>=storage.capacityKg-CARGO_WARNING_MARGIN_KG then return true end
    if status.fullyRaised~=true then return false end
    local catch=require("shipnet.automation_cargo").inspect(net,actor)
    return catch.ready==true and catch.status=="full"
end

function Fit:deviceStatus()
    local actor,net,ship=resolve(self.actorRef),resolve(self.netRef),resolve(self.shipRef)
    local r={visible=attached_device(self,actor),netAvailable=valid(net)}
    if not r.visible then return r end
    if self.built then
        r.basic=self.variant==variants.basic
        r.automationEnabled=actor.WinchAutomationEnabled==true
        r.automationStatus=self.cycle and self.cycle.status
        r.automationDrawKW=self.cycle and self.cycle.drawKW or 0
        r.power=self.power:builtStatus(actor)
        local now=os.time()
        if r.power.status~="native_input" and now>=self.nextPowerCheck then
            self.nextPowerCheck=now+2
            r.power=self.power:bindBuilt(actor,self.variant)
            self.powerState=r.power
            if r.power.status=="native_input" then self:_bindInteraction(actor) end
        end
    else
        r.power=opt(function() return self.power:inspect(actor) end)
    end
    if r.netAvailable then
        r.fullyRaised=opt(function() return net.FullyRaised end)
        r.netDropped=opt(function() return net.NetDropped end)
        r.netWeightKg=opt(function() return net.NetWeight end)
        if self.built then
            local weight,capacity=require("shipnet.automation_cargo").weight(net)
            r.netWeightKg=weight or r.netWeightKg
            r.netCapacityKg=capacity or opt(function() return net.InventoryMaxWeight end)
        end
    end
    if valid(ship) and not r.basic then
        r.storage=opt(function() return self:_storage():inspect(actor,ship) end)
        if r.storage and finite(r.storage.fillRatio) then
            local alarm=self.built==true and cargo_alarm(actor,net,r)
            self:setFill(r.storage.fillRatio,alarm,self.cycle and self.cycle.unloading)
        elseif self.lastFillUnloading then
            self:setFill(self.lastFill,self.lastFillAlarm,false)
        end
    end
    return r
end

function Fit:updateScreen(actor,status,pc)
    if not self.built then return end
    if not self.screen and os.time()<(self.screenRetry or 0) then return end
    local ok,reason=pcall(function()
        if not self.screen then
            pc=pc or FindFirstOf("VoyagePlayerController")
            if not valid(pc) or not pc:IsLocalController() or not same(pc:GetWorld(),actor:GetWorld()) then return end
            local glass=(self.variant.geometry or model).fitGeometry.display
            self.screen=require("shipnet.world_screen").mount(actor,glass,pc,function()
                local status=self:deviceStatus()
                if require("shipnet.screen_text").emptyBuffer(status.power) then
                    self.screen:update(status)
                    return
                end
                self:setAutomation(not actor.WinchAutomationEnabled)
                self.screen:update(self:deviceStatus())
            end,self.handlers and self.handlers.log,self.mesh)
        end
        self.screen:update(status)
    end)
    if ok then self.screenError=nil;return end
    self.screenRetry=os.time()+5
    if self.screen then self.screen:destroy();self.screen=nil end
    if self.handlers and self.handlers.log and self.screenError~=tostring(reason) then self.handlers.log("World screen: "..tostring(reason)) end
    self.screenError=tostring(reason)
end

function Fit:openScreen(pc)
    local actor=resolve(self.actorRef)
    if not self.built or not valid(actor) then return false,"Device unavailable" end
    self:updateScreen(actor,self:deviceStatus(),pc)
    if not self.screen then return false,self.screenError or "Screen loading" end
    return self.screen:open(pc)
end

function Fit:setAutomation(enabled)
    local actor=resolve(self.actorRef)
    if not self.cycle or not attached_device(self,actor) then return false,"Device unavailable" end
    self.cycle:setEnabled(actor,enabled)
    return true,self.cycle.status
end

local function game_time(actor)
    return StaticFindObject("/Script/Engine.Default__GameplayStatics"):GetTimeSeconds(actor)
end

function Fit:controlNet(action,automatic)
    local net,actor=resolve(self.netRef),resolve(self.actorRef)
    if not attached_device(self,actor) or not valid(net) then return false,"Stock winch unavailable" end
    if action~="raise" and action~="lower" then return false,"Unknown winch action" end
    local ok,err=pcall(function()
        local child=child_attachment(net,"SwitchChildActor","Switch")
        local switch=child and child.ChildActor
        assert(valid(switch),"Stock winch switch unavailable")
        local fromPanel=self.cycle and not automatic
        if action=="raise" then
            local now=fromPanel and game_time(actor)
            switch:TurnOFF()
            if fromPanel then self.cycle:adoptPanelRaise(switch:IsOn(),now,actor.WinchAutomationEnabled) end
        else
            if fromPanel and actor.WinchAutomationEnabled then self.cycle:setEnabled(actor,false) end
            switch:TurnON()
        end
        local rotor=switch.SwitchRotator
        if not valid(rotor) then return end
        local mesh,command=self.mesh,{}
        self.switchCommand=command
        local target=action=="raise" and -80 or 80
        local samples=0
        -- The fitted shaft and the stock lever rotate around the same forward axis.
        -- Read the stock animation so changes of direction do not jump to the end stop.
        local function follow()
            if self.mesh~=mesh or self.switchCommand~=command or not valid(rotor) then return true end
            local roll=opt(function() return rotor.RelativeRotation.Roll end)
            if not finite(roll) or not model.pose(mesh,self.hatchDegrees,roll) then return true end
            self.driveDegrees=roll
            samples=samples+1
            return math.abs(roll-target)<.01 or samples>=50
        end
        if not follow() then LoopInGameThreadWithDelay(20,follow) end
    end)
    if not ok then return false,tostring(err) end
    return true,action=="raise" and "Raise requested" or "Lower requested"
end

local function update_offset(self,value)
    local actor=resolve(self.actorRef)
    if not valid(actor) then return snapshot(self,"hidden") end
    if self.built then return snapshot(self,"built","Cannot move a fabricated controller with fit controls") end
    local blocked=guard(self,actor,"move")
    if blocked then return blocked end
    local ok,err=pcall(set_placement,self,actor,value)
    return snapshot(self,ok and "shown" or "error",not ok and tostring(err) or nil)
end

function Fit:show(value)
    local ok,requested=pcall(offsets,value or self.offset)
    if not ok then return snapshot(self,"error",tostring(requested)) end
    if valid(resolve(self.actorRef)) then
        for _,axis in ipairs(AXES) do if requested[axis]~=self.offset[axis] then return update_offset(self,requested) end end
        return snapshot(self)
    end
    forget(self)
    local success,target,why=pcall(choose_target,self)
    if not success or not target then return snapshot(self,success and (why or "no_mount") or "error",not success and tostring(target) or nil) end
    local created,err=pcall(create,self,target,requested)
    if not created then
        local cleanup=self:hide("map_change")
        return snapshot(self,"error",tostring(err)..(cleanup.visible and (" / "..tostring(cleanup.detail)) or ""))
    end
    return snapshot(self)
end

function Fit:move(axis,delta)
    if self.offset[axis]==nil or not finite(delta) then return snapshot(self,"error","Invalid adjustment") end
    local value=offsets(self.offset)
    value[axis]=value[axis]+delta
    if not finite(value[axis]) then return snapshot(self,"error","Invalid adjustment") end
    return update_offset(self,value)
end

function Fit:reset()
    return update_offset(self,offsets())
end

function Fit:pose(hatchDegrees,driveDegrees)
    if not valid(resolve(self.actorRef)) then return snapshot(self,"hidden") end
    hatchDegrees=hatchDegrees or self.hatchDegrees
    driveDegrees=driveDegrees or self.driveDegrees
    if not finite(hatchDegrees) or not finite(driveDegrees) then return snapshot(self,"error","Invalid pose angles") end
    self.switchCommand=nil
    hatchDegrees=math.max(0,math.min(hatchDegrees,model.maxHatchDegrees))
    local ok,err=model.pose(self.mesh,hatchDegrees,driveDegrees)
    if ok then self.hatchDegrees,self.driveDegrees=hatchDegrees,driveDegrees end
    return snapshot(self,ok and "shown" or "error",not ok and tostring(err) or nil)
end

local function update_lod(self,actor)
    local mesh=self.mesh
    if not mesh or mesh.lod==nil or mesh.lodError then return end
    local size
    if not (self.screen and self.screen.focus) then
        size=opt(function()
            local pc=self.lodPlayer
            if not valid(pc) then
                local game=StaticFindObject("/Script/Engine.Default__GameplayStatics")
                pc=game:GetPlayerController(actor,0)
                if not valid(pc) or not pc:IsLocalController() then return end
                self.lodPlayer=pc
            end
            return model.screenSize(mesh,pc)
        end)
    end
    model.updateLOD(mesh,size or 1)
    if mesh.lodError and self.handlers and self.handlers.log then
        self.handlers.log("Distant controller geometry: "..mesh.lodError)
    end
end

function Fit:tick()
    if not self.actorRef then return end
    local actor,mount,ship=resolve(self.actorRef),resolve(self.mountRef),resolve(self.shipRef)
    local reason="orphan"
    if valid(actor) and valid(mount) and valid(ship) then
        local parent=opt(function() return actor:GetAttachParentActor() end)
        local world=opt(function() return ship:GetWorld() end)
        if same(parent,mount) and same(world,resolve(self.worldRef)) then
            update_lod(self,actor)
            local net=resolve(self.netRef)
            local cargoChanged = false
            if self.cycle then
                local switchComponent=valid(net) and child_attachment(net,"SwitchChildActor","Switch")
                local lever=switchComponent and switchComponent.ChildActor
                if valid(lever) then
                    local ok,result=pcall(function()
                        local now=game_time(actor)
                        local changed=self.cycle:tick(actor,net,lever,now,function(action) return self:controlNet(action,true) end)
                        if self.variant==variants.basic and self.mesh.beacon then
                            local since=self.cycle.drawerWaitingSince
                            local lit=since~=nil and (now-since)%1.0<.5
                            local beaconOK,reason=pcall(model.setBeacon,self.mesh,lit)
                            if not beaconOK and self.handlers and self.handlers.log and reason~=self.lastBeaconError then
                                self.handlers.log("Basic amber light: "..tostring(reason))
                            end
                            self.lastBeaconError=not beaconOK and reason or nil
                        end
                        return changed
                    end)
                    if ok then
                        cargoChanged = result == true
                        self.lastCycleError=nil
                    else
                        self.cycle:interruptObservation()
                        self.cycle.status="Automation unavailable"
                        if result~=self.lastCycleError and self.handlers and self.handlers.log then self.handlers.log(tostring(result)) end
                        self.lastCycleError=result
                    end
                else
                    self.cycle:interruptObservation()
                end
            end
            local now=os.time()
            local unloading = self.cycle ~= nil and self.cycle.unloading == true
            if self.handlers and (cargoChanged or now~=self.lastFillUpdate or unloading~=(self.lastFillUnloading==true)) then
                self.lastFillUpdate=now
                local status=self:deviceStatus()
                if self.built then self:updateScreen(actor,status) end
            end
            if self.screen and self.screen.focus then
                local ok,err=pcall(self.screen.focusTick,self.screen)
                if not ok then
                    self.screen:close()
                    if self.handlers and self.handlers.log then self.handlers.log("Screen input: "..tostring(err)) end
                end
            end
            if now < self.nextWorldCheck then return end
            self.nextWorldCheck=now+2
            local current=opt(function()
                local player=FindFirstOf("VoyagePlayerController")
                if valid(player) and player:IsLocalController() then return player:GetWorld() end
            end)
            if not valid(current) or same(current,world) then return end
            reason="map_change"
        end
    end
    local cleared=self:hide(valid(actor) and reason or "map_change")
    if cleared.visible then return cleared end
    return snapshot(self,"lost_preview","Preview or parent no longer available. Show again on the loaded ship.")
end

local function child_actor(attachment)
    if valid(attachment) then return opt(function() return attachment.ChildActor end) end
end

local function local_point(maths,frame,component)
    if valid(component) then return vec(maths:InverseTransformLocation(frame,component:K2_GetComponentLocation())) end
end

local function corner_bounds(component,frame,maths)
    local low,high={},{}
    component:GetLocalBounds(low,high)
    local lo,hi=vec(low.min or low.Min or low),vec(high.max or high.Max or high)
    if not lo or not hi then return end
    local cframe=component:K2_GetComponentToWorld()
    local mn={X=math.huge,Y=math.huge,Z=math.huge}
    local mx={X=-math.huge,Y=-math.huge,Z=-math.huge}
    for i=0,7 do
        local p={X=(i&1)==0 and lo.X or hi.X,Y=(i&2)==0 and lo.Y or hi.Y,Z=(i&4)==0 and lo.Z or hi.Z}
        local v=vec(maths:InverseTransformLocation(frame,maths:TransformLocation(cframe,p)))
        if not v then return end
        for _,a in ipairs({"X","Y","Z"}) do mn[a]=math.min(mn[a],v[a]); mx[a]=math.max(mx[a],v[a]) end
    end
    return {min=mn,max=mx}
end

local function grow(bounds,point)
    if not bounds then return {min=vec(point),max=vec(point)} end
    for _,key in ipairs({"X","Y","Z"}) do
        bounds.min[key]=math.min(bounds.min[key],point[key])
        bounds.max[key]=math.max(bounds.max[key],point[key])
    end
    return bounds
end

local function footprint(maths,frame,actorFrame)
    local bounds
    local g=model.fitGeometry
    for _,x in ipairs({-g.halfWidthCm,g.halfWidthCm}) do
        for _,y in ipairs({-g.halfDepthCm,g.halfDepthCm}) do
            local p=maths:TransformLocation(actorFrame,{X=x,Y=y,Z=0})
            bounds=grow(bounds,maths:InverseTransformLocation(frame,p))
        end
    end
    return bounds
end

local function overlap(case,drawer)
    return {X=math.max(0,math.min(case.max.X,drawer.max.X)-math.max(case.min.X,drawer.min.X)),
        Y=math.max(0,math.min(case.max.Y,drawer.max.Y)-math.max(case.min.Y,drawer.min.Y))}
end

-- Stock visible surface sampled across the full 116 cm depth, in nominal
-- module coordinates. Entry one is at Z=0.5, measured rows are 1 cm apart.
local HOUSING_X_CM={55.95,56.12,56.29,56.46,56.65,56.82,56.99,57.24,57.53,57.81,58.10,
    58.39,58.67,58.95,59.23,59.54,59.92,60.31,60.70,61.09,61.46,61.85,62.24,62.64,63.12,
    63.64,64.14,64.65,65.09,65.35,65.62,65.89,66.15,66.78,66.82,66.89,66.95,66.99,67.06,
    67.28,68.07,68.85,69.64}
local function housing_relief(net,maths,actorFrame)
    local report={source="stock_render_depth_reference",build="25982825",sampleSpacingCm=1}
    local stock=opt(function() return net.SM_miscInt_e.StaticMesh end)
    if not valid(stock) or stock:GetFullName()~="StaticMesh /Game/AssetSets/Modules/Fishing/Fishing.Fishing" then
        report.status="stock_mesh_unverified";return report
    end
    local function relative(x,y)
        local world=maths:TransformLocation(actorFrame,{X=x,Y=y,Z=0})
        return maths:InverseTransformLocation(net:GetTransform(),world)
    end
    local center,x,y=relative(0,0),relative(1,0),relative(0,1)
    if math.abs(center.X-CABINET_ORIGIN.X)>.15 or math.abs(center.Y-CABINET_ORIGIN.Y)>.15 or math.abs(center.Z-CABINET_ORIGIN.Z)>.15
            or math.abs(x.X-center.X+1)>.00001 or math.abs(y.Y-center.Y+1)>.00001
            or math.abs(x.Y-center.Y)>.0001 or math.abs(y.X-center.X)>.0001 then
        report.status="outside_measured_pose";return report
    end
    local profile=model.fitGeometry.rightProfileCm
    local segment=2
    for i,stockX in ipairs(HOUSING_X_CM) do
        local z=i-.5
        while segment<#profile and z>profile[segment].Z do segment=segment+1 end
        local a,b=profile[segment-1],profile[segment]
        if z>=a.Z then
            local t=math.min(1,(z-a.Z)/(b.Z-a.Z))
            local caseX=a.X+t*(b.X-a.X)
            local gap=stockX-caseX
            if not report.minimumSampledGapXCm or gap<report.minimumSampledGapXCm then
                report.minimumSampledGapXCm,report.sampleHeightLocalCm=gap,z
            end
        end
    end
    report.status="nominal_relief_profile"
    -- Archived comparison of both rendered surfaces in the isolated Barge.
    -- The profile above is the authored edge before the body's actual bevels.
    report.testedModelReference={model="v03",stockBuild="25982825",nominalPose=true,gridSpacingCm=1,
        bodySamples=7859,bodyMinimumGapXCm=1.36,forwardBracketMinimumGapXCm=9.03}
    local shoe=model.fitGeometry.rightContact
    if shoe then
        report.rightBracket={method="tip_against_stock_render_reference",tipModelXcm=shoe.tipX,
            stockSurfaceModelXcm=shoe.surfaceX,insertionCm=shoe.tipX-shoe.surfaceX,
            atModelYcm=shoe.Y,atModelZcm=shoe.Z,stockBuild="25982825"}
    end
    return report
end

-- Clip a collision face to the outboard rail seat's rectangular footprint.
-- Interpolating Z keeps the height of sloping caps correct at the contact.
local function clip(f,axis,bound,sign)
    local result={}
    local a=f[#f]
    for _,b in ipairs(f) do
        local da,db=sign*(a[axis]-bound),sign*(b[axis]-bound)
        if (da>=0)~=(db>=0) then
            local t=da/(da-db)
            result[#result+1]={X=a.X+t*(b.X-a.X),Y=a.Y+t*(b.Y-a.Y),Z=a.Z+t*(b.Z-a.Z)}
        end
        if db>=0 then result[#result+1]=b end
        a=b
    end
    return result
end

-- In the Barge level instance, even the fixed housing can return zero
-- physics hits. Its stock StaticMesh BodySetup still contains the authored
-- oriented boxes. Search the narrow outer crossmember directly under the pad.
local function authored_support(c,maths,netFrame,mountFrame,actorFrame)
    local boxes=c.StaticMesh.BodySetup.AggGeom.BoxElems
    local pad=model.fitGeometry.outerSeat
    local cf=c:K2_GetComponentToWorld()
    local best
    for i=1,math.min(boxes:GetArrayNum(),64) do
        local b=boxes[i]
        local bf=maths:MakeTransform(b.Center,b.Rotation,{X=1,Y=1,Z=1})
        local points,netBounds={},nil
        for mask=0,7 do
            local localBox={X=((mask&1)==0 and -.5 or .5)*b.X,Y=((mask&2)==0 and -.5 or .5)*b.Y,
                Z=((mask&4)==0 and -.5 or .5)*b.Z}
            local world=maths:TransformLocation(cf,maths:TransformLocation(bf,localBox))
            local p=vec(maths:InverseTransformLocation(netFrame,world))
            points[mask+1]=vec(maths:InverseTransformLocation(actorFrame,world))
            netBounds=grow(netBounds,p)
        end
        if netBounds.max.X-netBounds.min.X<=40 and netBounds.max.X>=205 and netBounds.max.X<=225
            and netBounds.min.Y<=-205 and netBounds.max.Y>=-170 then
            for _,face in ipairs({{1,2,4,3},{5,6,8,7},{1,2,6,5},{3,4,8,7},{1,3,7,5},{2,4,8,6}}) do
                local f={points[face[1]],points[face[2]],points[face[3]],points[face[4]]}
                f=clip(clip(clip(clip(f,"X",pad.minX,1),"X",pad.maxX,-1),"Y",pad.minY,1),"Y",pad.maxY,-1)
                for _,p in ipairs(f) do
                    if not best or p.Z>best.padLocalCm.Z then
                        local wp=maths:TransformLocation(actorFrame,p)
                        local q=vec(maths:InverseTransformLocation(mountFrame,wp))
                        best={boxIndex=i,height=q.Z,padLocalCm=p,contactLocalCm=q,boxWinchBoundsCm=netBounds}
                    end
                end
            end
        end
    end
    return best
end

-- This stock mesh includes the outboard end rail as well as the winch casing.
-- Query only that verified fixed component; deck, crate and preview collisions
-- cannot be mistaken for a mounting face.
local function rail_survey(net,maths,mountFrame,actorFrame,seatHeight,caseBox)
    local r={status="unavailable",samples={},traceCount=0,traceMethod="stock_component_visibility"}
    local c=opt(function() return net.SM_miscInt_e end)
    if not valid(c) or not same(c:GetOwner(),net) then r.status="fixed_mesh_unavailable";return r end
    r.component=c:GetFullName()
    local bounds=opt(function() return corner_bounds(c,mountFrame,maths) end)
    if bounds then r.caseOuterXMinusRailEnvelopeXcm=caseBox.max.X-bounds.max.X end
    if c:GetCollisionResponseToChannel(3)~=2 then r.status="mesh_does_not_block_visibility";return r end
    local netFrame=net:GetTransform()
    local best
    for _,complex in ipairs({true,false}) do
        for _,x in ipairs({202,205,208,211,214,216,217}) do
            local row={}
            for _,y in ipairs({-230,-212,-190,-170,-149}) do
                local start=maths:TransformLocation(netFrame,{X=x,Y=y,Z=200})
                local finish=maths:TransformLocation(netFrame,{X=x,Y=y,Z=0})
                local hit,normal={},{}
                r.traceCount=r.traceCount+1
                if c:K2_LineTraceComponent(start,finish,complex,false,false,hit,normal,{},{}) then
                    local p=vec(hit.HitLocation or hit)
                    local n=vec(normal.HitNormal or normal)
                    if p and n then
                        local up=maths:InverseTransformDirection(netFrame,n)
                        if up.Z>0.7 then
                            local point=vec(maths:InverseTransformLocation(mountFrame,p))
                            row[#row+1]={x=x,y=y,z=point.Z,localCm=point}
                            r.samples[#r.samples+1]={netX=x,netY=y,localCm=point,complex=complex}
                        end
                    end
                end
            end
            -- A crossmember supports the unit across the drawer width. A solitary
            -- top hit on a side rail or bolt does not establish that surface.
            for i=1,#row do
                for j=i+1,#row do
                    local a,b=row[i],row[j]
                    if b.y-a.y>=35 and math.abs(a.z-b.z)<=1.5 then
                        local height=(a.z+b.z)*0.5
                        if not best or height>best.height then
                            best={height=height,netX=x,ySpanCm=b.y-a.y,localA=a.localCm,localB=b.localCm}
                        end
                    end
                end
            end
        end
        if best then r.traceComplex=complex;break end
    end
    if best then
        r.status,r.supportHeightCm,r.supportSample="crossmember_surface",best.height,best
        r.seatPlaneMinusSupportCm=seatHeight-best.height
    else
        r.status="no_crossmember_surface"
        local box=opt(function() return authored_support(c,maths,netFrame,mountFrame,actorFrame) end)
        if box then
            r.traceStatus="no_crossmember_surface"
            r.status,r.supportHeightCm,r.supportSample="authored_collision_box",box.height,box
            r.seatPlaneMinusSupportCm=seatHeight-box.height
        end
    end
    return r
end

local function measured(self,row)
    local actor,mount,net=resolve(self.actorRef),resolve(self.mountRef),resolve(self.netRef)
    if not valid(actor) or not valid(mount) then return end
    local maths=StaticFindObject(MATH)
    local frame,aframe=mount:GetTransform(),actor:GetTransform()
    row.measurementFrame=mount:GetFullName()
    row.datums={}
    for key,p in pairs(model.anchors) do
        row.datums[key]=vec(maths:InverseTransformLocation(frame,maths:TransformLocation(aframe,p)))
    end
    if not valid(net) then row.stockGeometry="unresolved"; return end
    row.stockGeometry="live"
    row.winchState={netDropped=opt(function() return net.NetDropped end),
        fullyRaised=opt(function() return net.FullyRaised end),
        currentLengthCm=opt(function() return net.CurrentLength end),
        containerLoweredOffsetCm=opt(function() return vec(net.ContainerLoweredOffset) end)}
    row.anchors={}
    local function add(role,c,bounds)
        if not valid(c) then return end
        local entry={role=role,object=c:GetFullName(),localCm=opt(function() return local_point(maths,frame,c) end)}
        if bounds then entry.boundsCm=opt(function() return corner_bounds(c,frame,maths) end) end
        table.insert(row.anchors,entry)
        return entry
    end
    local pivot,source=switch_anchor(net)
    local p=add(source or "switch",pivot)
    if p and p.localCm and row.datums.coupling then
        local t=row.datums.coupling
        row.couplingToSwitchCm=math.sqrt((p.localCm.X-t.X)^2+(p.localCm.Y-t.Y)^2+(p.localCm.Z-t.Z)^2)
    end
    local containerAttachment=child_attachment(net,"ContainerChildActor","Container")
    local current=add("drawer_child_origin",containerAttachment)
    local landing=add("drawer_landing",opt(function() return net.ContainerLocation end))
    for _,key in ipairs({"SM_Anchor_Reel","SM_Anchor_Reel1","SM_Anchor_Reel2","SM_Anchor_Reel3","SM_Anchor_Reel4","SM_miscInt_e","SM_miscInt_e1"}) do
        add("winch_mesh_"..key,opt(function() return net[key] end),true)
    end
    local caseBox=footprint(maths,frame,aframe)
    local seat=vec(maths:InverseTransformLocation(frame,maths:TransformLocation(aframe,{X=0,Y=0,Z=0})))
    -- The footprint includes the roof/side overhang past the relieved corner.
    -- Report the separately authored edge in model-local X/Z coordinates.
    row.footprint={caseBaseAabbCm=caseBox,rightProfileLocalCm=model.fitGeometry.rightProfileCm}
    row.housingRelief=opt(function() return housing_relief(net,maths,aframe) end)
    local traced,rail=pcall(rail_survey,net,maths,frame,aframe,seat.Z,caseBox)
    row.railSurvey=traced and rail or {status="trace_unavailable",detail=tostring(rail)}
    local container=child_actor(containerAttachment)
    if not valid(container) then return end
    local meshes=container:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.StaticMeshComponent"))
    local drawer
    local function add_mesh(c)
        local e=add("drawer_mesh",c,true)
        if e and e.boundsCm then
            drawer=grow(drawer,e.boundsCm.min)
            drawer=grow(drawer,e.boundsCm.max)
        end
    end
    if type(meshes.ForEach)=="function" then
        meshes:ForEach(function(i,v)
            if i>32 then return true end
            add_mesh(v:get())
        end)
    else
        for i=1,math.min(#meshes,32) do
            local c=meshes[i]
            add_mesh(valid(c) and c or opt(function() return c:get() end))
        end
    end
    if drawer then
        row.drawerTopCm=drawer.max.Z
        -- Signed vertical separation from the seat plane; it is not an intersection test.
        row.seatPlaneMinusDrawerTopCm=seat.Z-drawer.max.Z
        row.footprint.drawerCurrentAabbCm=drawer
        row.footprint.currentOverlapCm=overlap(caseBox,drawer)
        if current and current.localCm and landing and landing.localCm then
            -- ContainerLocation is the extended endpoint; the stock actuator
            -- translates its cargo actor from the current child origin to it.
            local extended={min={},max={}}
            for _,key in ipairs({"X","Y","Z"}) do
                local delta=landing.localCm[key]-current.localCm[key]
                extended.min[key],extended.max[key]=drawer.min[key]+delta,drawer.max[key]+delta
            end
            row.footprint.drawerAtLandingAabbCm=extended
            row.footprint.landingOverlapCm=overlap(caseBox,extended)
        end
    end
end

function Fit:report()
    -- A preview can be shown before the stock level finishes streaming. Pick up a
    -- verified live winch for measurements without moving an already-mounted inlet.
    if self.mode=="saved_barge_reference" and not valid(resolve(self.netRef)) then
        local ok,target=pcall(choose_target,self)
        if ok and target and valid(target.net) and same(target.ship,resolve(self.shipRef)) then
            self.netRef=ref(target.net)
        end
    end
    local row=snapshot(self)
    if row.visible then
        local ok,err=pcall(measured,self,row)
        if not ok then row.measurementError=tostring(err) end
    end
    return row
end

return {builtClass=BUILT,builtMount=built_mount,new=function()
    return setmetatable({offset=offsets(),power=power.new(),interaction=interaction.new(),hatchDegrees=0,driveDegrees=0},Fit)
end}
