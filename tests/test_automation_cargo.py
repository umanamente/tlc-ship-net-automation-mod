import unittest

from lupa.lua54 import LuaRuntime

from test_observer import SCRIPTS


FIXTURE = """
local nextId=0
local function object(class,owner)
  nextId=nextId+1
  local o={id=nextId,cls=class,owner=owner,valid=true,tags={}}
  function o:IsValid() return self.valid end
  function o:GetAddress() return self.id end
  function o:IsA(c) return self.cls==c end
  function o:IsActorBeingDestroyed() return self.dead==true end
  function o:GetOwner() return self.owner end
  function o:GetWorld() return self.world or world end
  function o:GetAttachParentActor() return self.parent end
  function o:GetLevel() return self.level end
  function o:ActorHasTag(tag) return self.tags[tag]==true end
  return o
end
function FName(s) return s end
local function wrapped(v)return {get=function()return v end}end
function inv(owner,capacity,n)
  local a=object("/Script/Voyage.VoyageInventoryWeightLimitedComponent",owner)
  a.rows={};a.Items={ForEach=function(_,fn)
    for k,v in pairs(a.rows)do fn(wrapped(k),wrapped(v)) end
  end};a.calls=0
  function a:GetTotalWeight() local s=0;for _,v in pairs(self.rows)do s=s+v.Item.mass*v.Data.ItemCount end;return s end
  function a:GetRemainingWeightSpace() return capacity-self:GetTotalWeight() end
  function a:GetCurrentMaxWeightLimit() return capacity end
  function a:GetNextEmptySlot()for k=0,n-1 do if self.rows[k]==nil then return k end end;return -1 end
  function a:IsSlotOccupied(k)return self.rows[k]~=nil end
  function a:IsValidSlotIndex(k)return k>=0 and k<n end
  function a:CanRemoveSlot(k)return not self.locked and self:IsSlotOccupied(k)end
  function a:CanSplitSlot(k)return self:CanRemoveSlot(k) and self.rows[k].Data.ItemCount>1 end
  function a:CanAddItem(it)return self.reject~=it end
  function a:CanAddToSlot(k,it)return self:IsValidSlotIndex(k) and (not self.rows[k]or self.rows[k].Item==it)end
  function a:EstimateAddAmount(it,req)return math.min(req, math.floor(self:GetRemainingWeightSpace()/it.mass)) end
  -- The stock weight-limited inventory overestimates space in occupied stacks.
  function a:EstimateAddAmountToSlot(k,it,req)return req end
  function a:TransferSlot(src,i,j,amount)
    self.calls=self.calls+1
    if self.failBefore then error('before commit')end
    if self.onTransfer then self.onTransfer()end
    local entry=src.rows[i];local data=entry.Data
    if (self.rows[j] and self.rows[j].Data.ItemCount or 0)+amount>entry.Item.MaxStackCount then return 0 end
    if not self.rows[j]then
      self.rows[j]={Item=entry.Item,AssetType=entry.AssetType,AssetName=entry.AssetName,Data={}}
      for k,v in pairs(data)do self.rows[j].Data[k]=v end
      self.rows[j].Data.ItemCount=0
    end
    self.rows[j].Data.ItemCount=self.rows[j].Data.ItemCount+amount;data.ItemCount=data.ItemCount-amount
    if data.ItemCount==0 then src.rows[i]=nil end
    if self.failAfter then error('after commit')end
    return amount
  end
  return a
end
world=object("World")
ship=object("/Game/Blueprints/Vehicles/BP_Boat_Barge.BP_Boat_Barge_C")
net=object("/Script/Voyage.VoyageModuleFishingActor");net.parent=ship
drawer=object("/Game/Blueprints/Interactives/Containers/BP_Inventory_Container_Fishing.BP_Inventory_Container_Fishing_C")
net.ContainerChildActor=object("ChildActorComponent",net); net.ContainerChildActor.ChildActor=drawer
cabinet=object("/Game/Mods/ShipNetAutomation/BP_Module_WinchAutomator.BP_Module_WinchAutomator_C");cabinet.parent=ship
net.FullyRaised=true;drawer.InteractEnabled=true;drawer.IsLocked=false
src=inv(drawer,30,16);net.InventoryComponent=src
function dest(cap,n) dst=inv(cabinet,cap,n);cabinet.VoyageInventoryWeightLimited=dst end
dest(50,6)
function item(name,mass,max) local a=object('Item');a.label=name;a.mass=mass;a.Weight=mass;a.MaxStackCount=max;return a end
iron=item('Iron',2,100); fish=item('Fish',1,11)
function array(values)
 return setmetatable(values,{__index={ForEach=function(a,fn)
   for i,v in ipairs(a)do fn(i,wrapped(v)) end
 end}})
end
function fields(values)
 return setmetatable(values,{__index={ForEach=function(a,fn)
   for _,v in ipairs(a)do fn(wrapped(v.prop),wrapped(v)) end
 end}})
end
function put(inventory,slot,it,count,custom)
 inventory.rows[slot]={Item=it,AssetName=it.label,AssetType={Name='Item'},Data={ItemCount=count,
   ItemData=array(custom and {18,237} or {}),ItemDataMap=fields(custom and {{prop='charge',Data=array({5,7})}}or{}),
   Timestamp=27,Flags=2,Version=1}}
end
cargo=require('shipnet.automation_cargo')
"""


class AutomatedCargoTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().package.path = str(SCRIPTS / "?.lua").replace("\\", "/")
        self.lua.execute(FIXTURE)

    def test_transfer_uses_only_bound_drawer_and_preserves_payload(self):
        self.lua.execute("""
        put(src,4,iron,3,true);put(src,7,fish,2)
        local pre=cargo.inspect(net,cabinet)
        assert(pre.ready and pre.space and pre.weight==8 and pre.capacity==30 and pre.remaining==5)
        assert(dst.calls==0 and cargo.count(net)==5)
        local r=cargo.unload(net,cabinet);assert(r.status=='moved' and r.remaining==2 and r.moved==3)
        local d=dst.rows[0].Data
        assert(d.ItemData[2]==237 and d.ItemDataMap[1].prop=='charge' and d.Timestamp==27 and d.Flags==2)
        assert(cargo.unload(net,cabinet).remaining==0 and cargo.unload(net,cabinet).status=='empty')
        assert(dst.calls==2 and src:GetTotalWeight()==0 and dst:GetTotalWeight()==8)
        """)

    def test_partial_weight_full_and_resume_after_player_removes_cargo(self):
        self.lua.execute("""
        dest(5,2);put(src,0,iron,5)
        local r=cargo.unload(net,cabinet);assert(r.moved==2 and r.remaining==3)
        assert(cargo.inspect(net,cabinet).status=='full' and cargo.unload(net,cabinet).moved==0)
        dst.rows[0]=nil
        local reloaded=require('shipnet.automation_cargo')
        assert(reloaded.unload(net,cabinet).moved==2 and src.rows[0].Data.ItemCount==1)
        assert(dst.calls==2)
        """)

    def test_manual_haul_redeploys_after_copying_every_stack_that_fits(self):
        self.lua.execute("""
        dest(5,3)
        local lowerCount=0
        local lever={on=true,IsOn=function(self)return self.on end}
        net.NetDropped=true;net.FullyRaised=false;drawer.InteractEnabled=false
        cabinet.WinchAutomationEnabled=true
        package.loaded['shipnet.automation_power']={new=function()
          return {consume=function(_,_,_,mode) return true,mode end}
        end}
        local cycle=require('shipnet.automation').new()
        local now=0
        local function poll()
          now=now+.25
          cycle:tick(cabinet,net,lever,now,function(action)
            assert(action=='lower' and lowerCount==0 and net.FullyRaised)
            assert(dst:GetTotalWeight()==5 and cargo.count(net)==5)
            lowerCount=lowerCount+1
            lever.on=true;net.NetDropped=true;net.FullyRaised=false;drawer.InteractEnabled=false
            return true
          end)
        end
        poll();poll()
        put(src,0,iron,5);put(src,1,fish,3)
        lever.on=false;net.NetDropped=false;net.FullyRaised=true;drawer.InteractEnabled=true
        for i=1,4 do poll() end
        assert(dst.calls==0 and lowerCount==0)
        for i=1,4 do poll() end
        assert(dst.calls==3 and lowerCount==0)
        for i=1,5 do poll() end
        assert(lowerCount==1 and dst.calls==3 and cabinet.WinchAutomationEnabled)
        assert(src.rows[0].Data.ItemCount==3 and src.rows[1].Data.ItemCount==2)
        """)

    def test_cheap_weight_never_enumerates_slots_or_uses_net_cache(self):
        self.lua.execute("""
        put(src,0,fish,2);net.NetWeight=0;net.InventoryMaxWeight=0
        src.Items.ForEach=function()error('fishing must not read rows')end
        local weight,limit=cargo.weight(net)
        assert(weight==2 and limit==30)
        src.GetCurrentMaxWeightLimit=function()return 300 end
        weight,limit=cargo.weight(net);assert(weight==2 and limit==300)
        for _,bad in ipairs({-1,math.huge,0/0}) do
            src.GetCurrentMaxWeightLimit=function()return bad end
            assert(cargo.weight(net)==nil)
        end
        src=inv(drawer,3.125,16);net.InventoryComponent=src
        put(src,0,item('Scrap',.125,100),17)
        weight,limit=cargo.weight(net);assert(weight==2.125 and limit==3.125)
        src.GetTotalWeight=function()return 0/0 end
        assert(cargo.weight(net)==nil)
        """)

    def test_cabinet_free_weight_reads_live_aggregate_only_from_bound_inventory(self):
        self.lua.execute("""
        put(dst,0,iron,20)
        dst.Items.ForEach=function()error('free weight must not enumerate slots')end
        local remaining=dst:GetRemainingWeightSpace()
        dst.GetRemainingWeightSpace=function()return remaining end
        assert(cargo.storageFreeWeight(net,cabinet)==10)
        remaining=-1;assert(cargo.storageFreeWeight(net,cabinet)==0)
        remaining=0/0;assert(cargo.storageFreeWeight(net,cabinet)==nil)
        remaining=10;cabinet.parent=nil
        assert(cargo.storageFreeWeight(net,cabinet)==nil)
        """)

    def test_full_drawer_unloads_in_six_powered_seconds_and_discards_paused_credit(self):
        self.lua.execute("""
            local scrap=item('Scrap',.5,100)
            put(src,0,scrap,60)
            local powered = true
            local lever={on=false,IsOn=function(self)return self.on end}
            cabinet.WinchAutomationEnabled=true
            package.loaded['shipnet.automation_power']={new=function()
                return {consume=function() return powered,"no_power" end}
            end}
            local cycle=require('shipnet.automation').new()
            local time=0
            local function poll(n)
                for i=1,n do
                    time=time+.25
                    cycle:tick(cabinet,net,lever,time,function() error('lowered during transfer') end)
                end
            end
            poll(5);assert(dst:GetTotalWeight()==0 and not cycle.unloading)
            poll(1);assert(dst:GetTotalWeight()==1 and cycle.unloading)
            powered=false;poll(20)
            assert(dst:GetTotalWeight()==1 and not cycle.unloading and cycle.unloadBudgetKg==nil)
            powered=true;poll(1);assert(dst:GetTotalWeight()==2 and cycle.unloading)
            poll(22);assert(dst:GetTotalWeight()==29.5 and src:GetTotalWeight()==.5 and cycle.unloading)
            poll(1);assert(dst:GetTotalWeight()==30 and src:GetTotalWeight()==0 and not cycle.unloading)
            assert(dst.rows[0].Data.ItemCount==60 and not dst.rows[1])
        """)

    def test_unsplittable_stack_waits_for_its_whole_weight(self):
        self.lua.execute("""
            put(src,0,iron,3,true)
            assert(cargo.unload(net,cabinet,5.99).status=='accruing' and dst.calls==0)
            local result=cargo.unload(net,cabinet,6)
            assert(result.status=='moved' and result.movedKg==6 and src:GetTotalWeight()==0 and dst.calls==1)
        """)

    def test_portions_fill_partial_stack_then_use_empty_slot(self):
        self.lua.execute("""
            local weed=item('Seaweed',.5,50)
            dest(100,3);put(dst,0,weed,50);put(dst,1,weed,49);put(src,2,weed,14)
            local result=cargo.unload(net,cabinet,1.25)
            assert(result.moved==1 and result.movedKg==.5 and dst.rows[1].Data.ItemCount==50)
            assert(cargo.unload(net,cabinet,.75).moved==1 and dst.rows[2].Data.ItemCount==1)
            assert(cargo.unload(net,cabinet,1.5).moved==3 and dst.rows[2].Data.ItemCount==4)
            assert(dst.rows[0].Data.ItemCount==50 and src.rows[2].Data.ItemCount==9 and dst.calls==3)
        """)

    def test_four_batches_per_second_with_whole_item_rounding_and_no_catchup(self):
        self.lua.execute("""
            put(src,0,item('Seaweed',.5,50),30)
            local cycle=require('shipnet.automation').new()
            for _,qty in ipairs({2,3,2,3}) do
                local before=dst:GetTotalWeight()
                for i=1,4 do assert(not cycle:unload(cabinet,net,.05)) end
                assert(dst:GetTotalWeight()==before)
                assert(cycle:unload(cabinet,net,.05))
                assert(dst:GetTotalWeight()==before+.5*qty)
            end
            assert(dst.calls==4 and dst:GetTotalWeight()==5)
            cycle:unload(cabinet,net,20)
            assert(dst.calls==5 and dst:GetTotalWeight()==6)
        """)

    def test_short_last_batch_scans_past_heavier_items_and_accepts_exact_fit(self):
        self.lua.execute("""
            local heavy,light=item('Heavy',.5,50),item('Light',.125,50)
            dest(10,4);put(dst,0,heavy,19)
            put(src,0,item('Oversize',2,50),2);put(src,1,light,2);put(src,2,heavy,1)
            put(src,3,item('Exact',.25,50),2)
            dst.EstimateAddAmount=function(_,_,n) return n end
            local cycle=require('shipnet.automation').new()
            assert(cycle:unload(cabinet,net,.25))
            assert(dst.calls==2 and dst:GetTotalWeight()==10)
            assert(not src.rows[1] and src.rows[2].Data.ItemCount==1 and src.rows[3].Data.ItemCount==1)
            assert(cargo.inspect(net,cabinet).status=='full')
            dest(1.125,3);put(dst,0,heavy,2)
            assert(cargo.inspect(net,cabinet).status=='full' and dst:GetRemainingWeightSpace()==.125)
        """)

    def test_full_stack_without_empty_slots_allows_other_catch_that_fits(self):
        self.lua.execute("""
            dest(100,2);put(dst,0,fish,11);put(dst,1,iron,3)
            put(src,0,fish,3);put(src,1,iron,1)
            assert(cargo.unload(net,cabinet,10).moved==1 and dst.rows[1].Data.ItemCount==4)
            assert(cargo.inspect(net,cabinet).status=='full' and dst.calls==1)
            src.rows[0]=nil;dst.rows[1]=nil;dest(100,1);put(dst,0,fish,11)
            assert(cargo.inspect(net,cabinet).space==false)
        """)

    def test_paced_portions_merge_restamped_cargo_and_keep_protected_timestamps(self):
        self.lua.execute("""
            put(src,0,fish,5);put(dst,0,fish,2)
            dst.rows[0].Data.Timestamp=300
            assert(cargo.unload(net,cabinet,1).movedKg==1)
            assert(dst.rows[0].Data.ItemCount==3 and not dst.rows[1])
            src.rows[0].Data.Flags=1;dst.rows[0].Data.Flags=1
            assert(cargo.unload(net,cabinet,1).movedKg==1)
            assert(dst.rows[0].Data.ItemCount==3 and dst.rows[1].Data.ItemCount==1)
        """)

    def test_metadata_error_inside_native_map_callback_cannot_mark_drawer_empty(self):
        self.lua.execute("""
        put(src,5,fish,2);src.rows[5].Data.ItemDataMap=nil
        local r=cargo.inspect(net,cabinet)
        assert(r.status=='unavailable' and r.remaining==nil and not r.space and dst.calls==0)
        """)

    def test_payload_and_occupied_slot_compatibility(self):
        self.lua.execute("""
        dest(50,1);put(src,1,iron,4);put(dst,0,iron,3)
        dst.rows[0].Data.Timestamp=987
        assert(cargo.unload(net,cabinet).status=='full' and dst.calls==0)
        dst.rows[0].Data.Timestamp=27
        assert(cargo.unload(net,cabinet).moved==4 and dst.rows[0].Data.ItemCount==7)
        put(src,3,iron,3,true);assert(cargo.unload(net,cabinet).status=='full')
        dest(5,1);assert(cargo.unload(net,cabinet).status=='full')
        put(src,5,fish,1);assert(cargo.unload(net,cabinet).moved==1 and src.rows[3].Data.ItemCount==3)
        """)

    def test_only_interactive_raised_drawer_mutates_and_no_foreign_or_detached_target(self):
        self.lua.execute("""
        put(src,2,iron,1);net.FullyRaised=false;drawer.InteractEnabled=false
        local r=cargo.inspect(net,cabinet);assert(r.status=='available' and r.space and not r.ready)
        assert(cargo.unload(net,cabinet).status=='not_ready')
        net.FullyRaised=true;drawer.InteractEnabled=true;drawer.IsLocked=true
        assert(cargo.unload(net,cabinet).status=='not_ready')
        drawer.IsLocked=false;cabinet.parent=nil;assert(cargo.inspect(net,cabinet).status=='unavailable')
        cabinet.parent=ship;cabinet.tags.Recycling=true;assert(cargo.inspect(net,cabinet).status=='unavailable')
        cabinet.tags.Recycling=nil;net.ContainerChildActor.ChildActor=ship
        assert(cargo.inspect(net,cabinet).status=='unavailable' and dst.calls==0)
        """)

    def test_failure_and_reentrant_native_notification_do_not_duplicate(self):
        self.lua.execute("""
        put(src,4,fish,3);dst.failBefore=true
        assert(cargo.unload(net,cabinet).status=='unavailable' and cargo.count(net)==3)
        dst.failBefore=false;dst.failAfter=true
        dst.onTransfer=function()assert(cargo.unload(net,cabinet).status=='unavailable')end
        local r=cargo.unload(net,cabinet)
        assert(r.status=='moved' and r.moved==3 and r.remaining==0 and dst.rows[0].Data.ItemCount==3)
        assert(cargo.unload(net,cabinet).status=='empty' and dst.calls==2)
        """)

    def test_streamed_winch_on_its_own_barge_and_same_named_foreign_level(self):
        self.lua.execute("""
        put(src,2,iron,1)
        net.world={IsValid=function()return true end,GetAddress=function()return 391 end}
        drawer.world=net.world;net.parent=nil
        local level=src;net.level=level
        ship.LevelInstanceComponent={IsValid=function()return true end,GetOwner=function()return ship end,
          LoadingLevel={IsValid=function()return true end,GetLoadedLevel=function()return level end}}
        assert(cargo.inspect(net,cabinet).ready and cargo.unload(net,cabinet).moved==1)
        net.level=drawer
        assert(cargo.inspect(net,cabinet).status=='unavailable')
        """)

    def test_inconsistent_counts_and_post_transfer_read_errors_are_unconfirmed(self):
        self.lua.execute("""
        put(src,2,fish,3)
        dst.TransferSlot=function(self,source,i,j,n)
          source.rows[i].Data.ItemCount=2
          error('one-sided removal')
        end
        assert(cargo.unload(net,cabinet).status=='unconfirmed')
        dst.TransferSlot=function(self,source,i,j,n)
          put(self,j,fish,n);source.rows[i]=nil
          self.Items.ForEach=function()error('unreadable after native commit')end
          return n
        end
        assert(cargo.unload(net,cabinet).status=='unconfirmed')
        """)

    def test_payload_change_on_failed_call_or_unrelated_slot_cannot_be_retried(self):
        self.lua.execute("""
        put(src,4,fish,2,true);put(dst,1,iron,1,true)
        dst.TransferSlot=function(self)
          self.rows[1].Data.ItemDataMap[1].Data[2]=12
          error('metadata changed')
        end
        assert(cargo.unload(net,cabinet).status=='unconfirmed')
        dst.TransferSlot=function(self,source,i,j,n)
          put(self,j,fish,n,true);source.rows[i]=nil
          self.rows[1].Data.Timestamp=299
          return n
        end
        assert(cargo.unload(net,cabinet).status=='unconfirmed')
        """)

    def test_native_new_destination_timestamp_and_unexpected_payload_rewrite(self):
        self.lua.execute("""
        put(src,4,fish,2,true)
        local transfer=dst.TransferSlot
        dst.TransferSlot=function(self,source,i,j,n)
          local result=transfer(self,source,i,j,n)
          self.rows[j].Data.Timestamp=137
          self.rows[j].Data.Version=15
          return result
        end
        assert(cargo.unload(net,cabinet).moved==2)
        put(src,4,fish,2,true)
        dst.TransferSlot=function(self,source,i,j,n)
          local result=transfer(self,source,i,j,n)
          self.rows[j].Data.ItemData[2]=8
          return result
        end
        assert(cargo.unload(net,cabinet).status=='unconfirmed')
        """)
