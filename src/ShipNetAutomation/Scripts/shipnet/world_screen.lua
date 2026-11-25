local Panel=require("shipnet.panel")
local display=require("shipnet.display")
local text=require("shipnet.screen_text")
local valid=require("shipnet.observer").valid
local Screen={}
Screen.__index=Screen
local width=960
-- The caption and status sit above the painted button and its projected input region.
local switch={x=.645,y=.365,w=.315,h=.335}
local function rgb(r,g,b) return {R=r,G=g,B=b,A=1} end
local ink,bright,muted=rgb(.008,.023,.019),rgb(.56,1,.72),rgb(.26,.54,.39)
local track,red=rgb(.017,.045,.034),rgb(1,.13,.095)
local buttonColors={
    [true]={face=rgb(.064,.51,.14),hover=rgb(.11,.65,.21),rim=rgb(.36,.82,.41),
        edge=rgb(.12,.32,.19),text=rgb(.010,.024,.012),status=rgb(.55,.94,.55)},
    [false]={face=rgb(.63,.058,.048),hover=rgb(.85,.10,.09),rim=rgb(.94,.29,.24),
        edge=rgb(.39,.057,.06),text=rgb(.039,.009,.009),status=rgb(1,.40,.35)},
}
local function mathlib() return StaticFindObject("/Script/Engine.Default__KismetMathLibrary") end
local function slot(canvas,child,x,y,w,h)
    local s=canvas:AddChildToCanvas(child)
    s:SetAutoSize(false)
    s:SetPosition({X=x,Y=y})
    s:SetSize({X=w,Y=h})
    return s
end
local function cell(self,parent,obj,x,y,w,h)
    return slot(parent,obj,x*width,y*self.h,w*width,h*self.h)
end
local function color(label,c) label:SetColorAndOpacity({SpecifiedColor=c,ColorUseRule=0}) end
local function block(self,parent,c,x,y,w,h)
    local b=self.factory:_make("Border",self.host.WidgetTree)
    b:SetBrushColor(c)
    return b,cell(self,parent,b,x,y,w,h)
end
local function label(self,parent,size,tint,x,y,w,h,align)
    local b=self.factory:_make("TextBlock",self.host.WidgetTree)
    local f=b.Font
    if valid(self.font) then f.FontObject=self.font end
    f.Size=size
    b:SetFont(f)
    b:SetAutoWrapText(false)
    b:SetJustification(align or 0)
    color(b,tint)
    cell(self,parent,b,x,y,w,h)
    return b
end
local function layer(self)
    local canvas=self.factory:_make("CanvasPanel",self.host.WidgetTree)
    cell(self,self.host.WidgetTree.RootWidget,canvas,0,0,1,1)
    return canvas
end
local function make_face(self)
    local host=self.host
    self.font=StaticFindObject("/Game/UI/VoyageRoboto.VoyageRoboto")
    if not valid(self.font) then
        local ok,font=pcall(LoadAsset,"/Game/UI/VoyageRoboto.VoyageRoboto")
        if ok then self.font=font end
    end
    block(self,host.WidgetTree.RootWidget,ink,0,0,1,1)
    local face=layer(self)
    self.face=face
    self.catch=label(self,face,22,muted,.045,.10,.42,.20)
    self.weight=label(self,face,35,bright,.044,.31,.595,.30)
    self.power=label(self,face,18,muted,.046,.56,.49,.16)
    block(self,face,track,.045,.76,.91,1/6)
    self.fill,self.fillSlot=block(self,face,bright,.045,.76,.91,1/6)
    for i=1,23 do block(self,face,ink,.045+.91*i/24,.76,.003,1/6) end
    self.warningLayer=layer(self)
    block(self,self.warningLayer,rgb(.044,.008,.006),0,0,1,1)
    self.warning=label(self,self.warningLayer,30,red,.05,.54,.90,.32,1)
    self.warning.Slot:SetAutoSize(true)
    self.warning.Slot:SetAlignment({X=.5,Y=.5})
    self.switchLayer=layer(self)
    self.auto=label(self,self.switchLayer,19,muted,switch.x,.19,.19,.16)
    self.mode=label(self,self.switchLayer,19,bright,.835,.19,.125,.16,2)
    self.switchBack=block(self,self.switchLayer,ink,switch.x,switch.y,switch.w,switch.h)
    self.switchFace=block(self,self.switchLayer,ink,switch.x+.004,switch.y,switch.w-.008,switch.h*.86)
    self.switchRim=block(self,self.switchLayer,ink,switch.x+.004,switch.y,switch.w-.008,.012)
    self.action=label(self,self.switchLayer,25,ink,switch.x+switch.w/2,switch.y+switch.h*.43,0,0,1)
    self.action.Slot:SetAutoSize(true)
    self.action.Slot:SetAlignment({X=.5,Y=.5})
end

local function paintButton(self,enabled)
    local palette=buttonColors[enabled]
    local f=self.focus
    self.switchBack:SetBrushColor(palette.edge)
    self.switchFace:SetBrushColor(f and f.hovered and palette.hover or palette.face)
    self.switchRim:SetBrushColor(palette.rim)
    local shift={X=0,Y=f and f.pressed and self.h*.035 or 0}
    self.switchFace:SetRenderTranslation(shift)
    self.switchRim:SetRenderTranslation(shift)
    self.action:SetRenderTranslation(shift)
    color(self.mode,palette.status)
    color(self.action,palette.text)
end

local function mount_component(self,class,transform)
    local actor=self.actor
    local c=actor:AddComponentByClass(StaticFindObject(class),false,transform,true)
    assert(valid(c),"Could not add "..class)
    self.parts[#self.parts+1]=c
    c:SetMobility(2)
    c:SetCollisionEnabled(0)
    c:SetGenerateOverlapEvents(false)
    actor:FinishAddComponent(c,false,transform)
    return c
end
local function mount_bolt(self)
    local g=self.glass
    local z=g.maxZ-.29*self.height
    local t=mathlib():MakeTransform({X=self.cx,Y=g.Y+.04,Z=z},{Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
    local c=mount_component(self,"/Script/ProceduralMeshComponent.ProceduralMeshComponent",t)
    c:SetVisibility(false,false)
    c:SetLightingChannels(false,false,false)
    local verts,normals,uv={},{},{}
    for i,p in ipairs({{.10,.16},{-.10,-.005},{-.007,-.005},{-.095,-.16},{.10,.038},{.008,.038}}) do
        verts[i]={X=p[1]*self.height,Y=0,Z=p[2]*self.height}
        normals[i]={X=0,Y=1,Z=0}
        uv[i]={X=p[1]+.5,Y=.5-p[2]}
    end
    -- Two convex halves of a lightning bolt, clockwise on the cabinet face.
    c:CreateMeshSection_LinearColor(0,verts,{0,1,5,1,2,5,2,3,4,2,4,5},normals,uv,{},{},{},{},{},false,false)
    self.boltMaterial=require("shipnet.cargo_meter").blinkMaterial(c,rgb(.78,0,0),.002,.30)
    self.bolt=c
end
function Screen.mount(actor,aperture,pc,onToggle,log,mesh)
    local g={minX=aperture.minX+.32,maxX=aperture.maxX-.32,minZ=aperture.minZ+.32,maxZ=aperture.maxZ-.32,Y=aperture.lcdY}
    local w,h=g.maxX-g.minX,g.maxZ-g.minZ
    local self=setmetatable({actor=actor,glass=g,cx=(g.minX+g.maxX)/2,cz=(g.minZ+g.maxZ)/2,
        width=w,height=h,h=math.floor(width*h/w+.5),factory=Panel.new({}),parts={},cache={},onToggle=onToggle,log=log},Screen)
    local ok,err=pcall(function()
        self.host=Panel.host(pc)
        make_face(self)
        local transform=mathlib():MakeTransform({X=self.cx,Y=g.Y,Z=self.cz},
            {Pitch=0,Yaw=90,Roll=0},{X=1,Y=w/width,Z=h/self.h})
        local c=mount_component(self,"/Script/UMG.WidgetComponent",transform)
        self.component=c
        c:SetWidgetSpace(0)
        c:SetDrawSize({X=width,Y=self.h})
        c:SetPivot({X=.5,Y=.5})
        c:SetTwoSided(false)
        c:SetMaterial(0,display.crtMaterial())
        c:SetBackgroundColor(ink)
        c:SetManuallyRedraw(true)
        c:SetTickWhenOffscreen(true)
        c:SetWidget(self.host)
        assert(valid(c:GetWidget()) and c:GetWidget():GetAddress()==self.host:GetAddress(),"World widget did not bind")
        -- Keep the terminal's scanlines and distortion while preserving the UI's status colors.
        local lcd=c:GetMaterialInstance()
        assert(valid(lcd),"World widget did not create its LCD material")
        lcd:SetVectorParameterValue(FName("TintBase",EFindName.FNAME_Find),rgb(1,1,1))
        local lensTransform=mathlib():MakeTransform({X=self.cx,Y=aperture.lensY,Z=self.cz},
            {Pitch=0,Yaw=0,Roll=0},{X=1,Y=1,Z=1})
        self.lens=mount_component(self,"/Script/ProceduralMeshComponent.ProceduralMeshComponent",lensTransform)
        self.lens:SetTranslucentSortPriority(2)
        self.lensMaterial=display.lens(self.lens,aperture.maxX-aperture.minX,aperture.maxZ-aperture.minZ)
        local boltOK,why=pcall(mount_bolt,self)
        if not boltOK and log then log("Power warning glyph: "..tostring(why)) end
        self.mesh=mesh
        if mesh then require("shipnet.model").setScreenMounted(mesh,true) end
    end)
    if not ok then self:destroy();error(err,0) end
    return self
end
local function centerWarning(self)
    self.warning:ForceLayoutPrepass()
    local captionHeight=self.warning:GetDesiredSize().Y
    local boltHeight=valid(self.bolt) and self.h*.32 or 0
    local gap=boltHeight>0 and self.h*.075 or 0
    self.warning.Slot:SetPosition({X=width/2,Y=(self.h+boltHeight+gap)/2})
    if boltHeight>0 then
        local fromTop=(self.h-gap-captionHeight)/2
        self.bolt:K2_SetRelativeLocation({X=self.cx,Y=self.glass.Y+.04,
            Z=self.glass.maxZ-fromTop*self.height/self.h},false,{},true)
    end
end
local function syncSwitchInput(self,f)
    local visible=not self.empty
    if visible~=f.switchVisible then
        f.switchVisible=visible
        f.clicked=false
        f.hovered,f.pressed=false,false
        f.button:SetVisibility(visible and 0 or 1)
        f.button:SetIsEnabled(false)
        f.needsFocus=visible
    end
end
function Screen:update(status)
    self.status=status
    local tag,locale=text.culture()
    local raw={tag,locale,status.netCapacityKg or false,status.netWeightKg or false,status.automationEnabled==true,
        status.automationDrawKW or false,text.emptyBuffer(status.power)}
    local changed=false
    for i,v in ipairs(raw) do if self.cache[i]~=v then changed=true;break end end
    if not changed then return end
    local r=text.readout(status,tag,locale)
    if self.cache[1]~=tag and valid(self.actor) then self.actor.WinchScreenAction.Text=FText(r.prompt) end
    for _,key in ipairs({"catch","weight","power","action"}) do self[key]:SetText(FText(r[key])) end
    if self.cache[1]~=tag then self.warning:SetText(text.noPower(r.warning)) end
    self.auto:SetText(FText(r.label))
    self.mode:SetText(FText("• "..r.mode))
    self.face:SetVisibility(r.empty and 1 or 0)
    self.warningLayer:SetVisibility(r.empty and 0 or 1)
    self.switchLayer:SetVisibility(r.empty and 1 or 0)
    if r.empty and (not self.empty or self.cache[1]~=tag) then centerWarning(self) end
    self.empty=r.empty
    if self.focus then syncSwitchInput(self,self.focus) end
    paintButton(self,status.automationEnabled==true)
    if valid(self.bolt) then self.bolt:SetVisibility(r.empty,false) end
    self.fillSlot:SetSize({X=.91*width*r.fraction,Y=self.h/6})
    self.fill:SetVisibility(r.fraction>0 and 0 or 1)
    self.component:RequestRenderUpdate()
    self.cache=raw
end

local function project(self,f,u,v)
    local g=self.glass
    local world=mathlib():TransformLocation(self.actor:GetTransform(),{
        X=g.minX+u*self.width,Y=g.Y,Z=g.maxZ-v*self.height})
    local out={}
    if f.layout:ProjectWorldLocationToWidgetPosition(f.pc,world,out,false) then
        return out.ScreenPosition or out
    end
end

function Screen:focusTick()
    local f=self.focus
    if not f then return end
    if not valid(f.pc) or not valid(f.pc.Pawn) or f.pc.Pawn:GetAddress()~=f.pawn or
        not valid(f.camera) or not valid(f.overlay) or not f.overlay:IsInViewport() or not f.pc.bShowMouseCursor then
        self:close();return
    end
    if not f.switchVisible then return end
    local a=project(self,f,switch.x,switch.y)
    local b=project(self,f,switch.x+switch.w,switch.y+switch.h)
    local hovered,pressed=false,false
    if a and b and b.X>a.X and b.Y>a.Y then
        f.slot:SetPosition({X=a.X,Y=a.Y})
        f.slot:SetSize({X=b.X-a.X,Y=b.Y-a.Y})
        f.button:SetIsEnabled(true)
        if f.needsFocus then f.button.Button:SetKeyboardFocus();f.needsFocus=false end
        hovered=f.button.Button:IsHovered()
        pressed=f.button.Button:IsPressed()
    else
        f.button:SetIsEnabled(false)
        f.clicked=false
    end
    if hovered~=f.hovered or pressed~=f.pressed then
        f.hovered,f.pressed=hovered,pressed
        paintButton(self,self.status.automationEnabled==true)
        self.component:RequestRenderUpdate()
    end
    if f.clicked then
        f.clicked=false
        self.onToggle()
    end
end

function Screen:open(pc)
    if self.focus then return true end
    if not valid(pc) or not valid(pc.Pawn) or pc.bShowMouseCursor then return false,"Game input unavailable" end
    local f={pc=pc,pawn=pc.Pawn:GetAddress(),previous=pc:GetViewTarget(),cursor=pc.bShowMouseCursor}
    self.focus=f
    local ok,err=pcall(function()
        local p=self.actor:K2_GetActorLocation()
        f.camera=pc:GetWorld():SpawnActor(StaticFindObject("/Script/Engine.CameraActor"),
            {X=p.X,Y=p.Y,Z=p.Z},{Pitch=0,Yaw=0,Roll=0})
        assert(valid(f.camera),"Screen camera unavailable")
        local cam=f.camera
        cam:K2_GetRootComponent():SetMobility(2)
        assert(cam:K2_AttachToComponent(self.actor:K2_GetRootComponent(),FName("None",EFindName.FNAME_Find),2,2,2,false),
            "Screen camera attachment failed")
        cam:K2_SetActorRelativeLocation({X=self.cx,Y=self.glass.Y+self.width*1.08,Z=self.cz},false,{},true)
        cam:K2_SetActorRelativeRotation({Pitch=0,Yaw=-90,Roll=0},false,{},true)
        cam.CameraComponent:SetFieldOfView(60)
        cam.CameraComponent.bConstrainAspectRatio=false
        cam.CameraComponent.bOverrideAspectRatioAxisConstraint=true
        cam.CameraComponent.AspectRatioAxisConstraint=1 -- Keep horizontal FOV on narrower viewports.
        f.overlay,f.input=Panel.host(pc)
        f.button=Panel.inputButton(pc,f.input)
        assert(valid(f.button) and valid(f.button.Button),"Screen input target unavailable")
        f.slot=slot(f.overlay.WidgetTree.RootWidget,f.button,0,0,1,1)
        -- Slate owns clicks and keyboard focus while zoomed. All visible pixels
        -- still come from the scene component, including when the camera leaves.
        f.button:SetRenderOpacity(0)
        syncSwitchInput(self,f)
        local address=f.button:GetAddress()
        f.pre,f.post=RegisterHook(Panel.clickEvent,function(ctx)
            if self.focus~=f or not f.switchVisible or not f.button:GetIsEnabled() then return end
            local obj=ctx:get()
            if valid(obj) and obj:GetAddress()==address then f.clicked=true end
        end)
        f.layout=StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary")
        f.overlay:SetVisibility(4)
        f.overlay:AddToViewport(9790)
        assert(f.overlay:IsInViewport(),"Screen input could not open")
        local hud=pc:GetPlayerFocusWidget()
        if valid(hud) and hud:IsA("/Game/UI/Game/HUD/BP_VoyageIngameHud.BP_VoyageIngameHud_C") then
            f.hud,f.hudOpacity=hud,hud:GetRenderOpacity()
            hud:SetRenderOpacity(0)
        end
        pc:SetViewTargetWithBlend(cam,.32,3,2,false)
        f.view=true
        pc:SetIgnoreMoveInput(true);f.move=true
        pc:SetIgnoreLookInput(true);f.look=true
        pc.bShowMouseCursor=true;f.mouse=true
        f.mode=true
        f.input:SetInputMode_UIOnlyEx(pc,f.overlay,0,true)
    end)
    if not ok then self:close();if self.log then self.log("Screen focus: "..tostring(err)) end;return false,tostring(err) end
    return true
end

function Screen:close()
    local f=self.focus
    if not f then return end
    self.focus=nil
    if f.hovered or f.pressed then
        pcall(function()
            paintButton(self,self.status.automationEnabled==true)
            self.component:RequestRenderUpdate()
        end)
    end
    if f.pre and f.post then pcall(UnregisterHook,Panel.clickEvent,f.pre,f.post) end
    if valid(f.overlay) then pcall(function() f.overlay:RemoveFromParent() end) end
    if valid(f.hud) then pcall(function() f.hud:SetRenderOpacity(f.hudOpacity) end) end
    if valid(f.pc) then
        local pc=f.pc
        if f.view then pcall(function()
            local target=valid(f.previous) and f.previous or pc.Pawn
            if valid(target) then pc:SetViewTargetWithBlend(target,0,0,0,false) end
        end) end
        if f.move then pcall(function() pc:SetIgnoreMoveInput(false) end) end
        if f.look then pcall(function() pc:SetIgnoreLookInput(false) end) end
        if f.mode then pcall(function() f.input:SetInputMode_GameOnly(pc,true);f.input:SetFocusToGameViewport() end) end
        if f.mouse then pcall(function() pc.bShowMouseCursor=f.cursor end) end
    end
    if valid(f.camera) then pcall(function() f.camera:K2_DestroyActor() end) end
end
function Screen:destroy()
    self:close()
    if self.mesh and valid(self.mesh.body) then
        pcall(require("shipnet.model").setScreenMounted,self.mesh,false)
    end
    for i=#self.parts,1,-1 do
        local c=self.parts[i]
        if valid(c) then pcall(function() c:K2_DestroyComponent(self.actor) end) end
    end
    self.parts={}
end
return Screen
