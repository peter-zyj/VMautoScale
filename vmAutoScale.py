from pyVim import connect
from pyVmomi import vim
import os,optparse,sys,datetime
import yaml,re,time
import atexit
from multiprocessing import Process, Queue
from threading import Thread
import ssl,subprocess

#new release 11:
#secure data transfer (NA)
#bug fix for the si connection argument transfer between function and multi-process
####
#speed up the Clone policy by deploy the local source clone
####
#add console support for telnet UCSIP port
###NB::  seems Serial Port is not ok for the 1st deployment, the deployment seems not compatiable with OVF/OVA deploy
#Still add Serial Port, but after the 1st deployment and before the multiple clone


sslContext = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
sslContext.verify_mode = ssl.CERT_NONE
sleepTime = 0

class env(object):
    def __init__(self, conf):
        self.vCenter = ""
        self.vUser = ""
        self.vPasswd = ""
        self.UCS = ""
        self.uUser = ""
        self.uPasswd = ""
        self.ovf = ""
        self.range = ""
        self.crashFile = ""
        self.prefix = ""
        self.limit = ""
        self.ucs = ""
        self.dcName = ""
        self.cloneSource = ""
        self.__config(conf)
        
    def __config(self,conf):
        with open(conf,"r") as f:
            cont = f.read()
        content = yaml.load(cont)
        try:
            self.vCenter = content["vCenter"]
            self.vUser = content["vUser"]
            self.vPasswd = content["vPasswd"]
            self.UCS = content["UCS"]
            self.uUser = content["uUser"]
            self.uPasswd = content["uPasswd"]
            self.ovf = content["ovf"]
            self.range = content["range"]
            self.crashFile = content["crashFile"]
            self.dsprefix = content["dsprefix"]
            self.vmprefix = content["vmprefix"]
            self.limit = content["limit"]
            self.dcName = content["dcName"]
            self.cloneSource = content["cloneSource"]
        except Exception as e:
            print "Err::Config.yaml has the exception!"
            print e
            sys.exit(1)


def rangeVMlist(ran):
    ran = str(ran)
    if ',' in ran:
        ran = ran.split(',')
    elif " " in ran:
        ran = ran.split()
    else:
        ran = [ran]

    ll = []
    for i in ran:
          if '-' not in i:
                  ll.append(int(i))
          else:
                  ll+=range(int(i.split('-')[0]),int(i.split('-')[1])+1)

    ll.sort()
    return ll


def keep_lease_alive(lease):
    """
    Keeps the lease alive while POSTing the VMDK.
    """
    while(True):
        time.sleep(5)
        try:
            # Choosing arbitrary percentage to keep the lease alive.
            lease.HttpNfcLeaseProgress(50)
            if (lease.state == vim.HttpNfcLease.State.done):
                return
            # If the lease is released, we get an exception.
            # Returning to kill the thread.
        except:
            return

def ImportOVF(ucs,uuser,upasswd,ds,ovf,name):
    si = connect.SmartConnect(host=ucs,user=uuser,pwd=upasswd,sslContext=sslContext)
#   si = connect.SmartConnect(host=ucs,user=uuser,pwd=upasswd)
    datacenter_list = si.content.rootFolder.childEntity
    datacenter_obj = datacenter_list[0]
    datastore_list = datacenter_obj.datastoreFolder.childEntity
    datastore_obj = ""
    for x in datastore_list:
        if ds in x.name:
            datastore_obj = x
    try:
        if datastore_obj == "":
            print "No hulk store exist, choose the default one:First one"
            datastore_obj = datastore_list[0]
    except:
        pass

    cluster_list = datacenter_obj.hostFolder.childEntity
    cluster_obj = cluster_list[0]
    resource_pool_obj = cluster_obj.resourcePool
    manager = si.content.ovfManager
    spec_params = vim.OvfManager.CreateImportSpecParams()
    spec_params.entityName = name
    ovfd = open(ovf,'r').read()
    objs = {"datacenter": datacenter_obj,"datastore": datastore_obj,"resource pool": resource_pool_obj}
    import_spec = manager.CreateImportSpec(ovfd,objs["resource pool"],objs["datastore"],spec_params)
    lease = objs["resource pool"].ImportVApp(import_spec.importSpec,objs["datacenter"].vmFolder)
    while(True):
        if (lease.state == vim.HttpNfcLease.State.ready):
            url = lease.info.deviceUrl[0].url.replace('*', ucs)
            keepalive_thread = Thread(target=keep_lease_alive, args=(lease,))
            keepalive_thread.start()
            print "url-first::",url
            vmdk1 = ovf.replace(".ovf","_disk1.vmdk")
            vmdk2 = ovf.replace(".ovf","_disk2.vmdk")
            # if vmdk has been mis-pointed by the faulty name, then "Capacity of uploaded disk is larger than requested" report
            if (not os.path.isfile(vmdk1)) and (not os.path.isfile(vmdk2)):
                vmdk1 = ovf.replace(".ovf","-disk1.vmdk")
                vmdk2 = ovf.replace(".ovf","-disk2.vmdk")
            if (os.path.isfile(vmdk1)) and (not os.path.isfile(vmdk2)):
                vmdk1 = ovf.replace(".ovf","_disk0.vmdk")
                vmdk2 = ovf.replace(".ovf","_disk1.vmdk")
            try:
                curl_cmd = ("curl -Ss -X POST --insecure -T %s -H 'Content-Type: application/x-vnd.vmware-streamVmdk' %s" % (vmdk1, url))
                result = subprocess.check_output(curl_cmd,stderr=subprocess.STDOUT,shell=True)
                if "Capacity of uploaded disk is larger than request" in result:
                    print result
                    raise 
            except Exception as e:
                print "Yijun:debug:Curl:vmdk1:",curl_cmd
                print "Yijun:debug:Curl:vmdk1:err:",e
                print "Yijun:debug:Curl:vmdk1:path:",vmdk1
            url = url.replace('disk-0', "disk-1")
            print "url-second::",url
            try:
                curl_cmd = ("curl -Ss -X POST --insecure -T %s -H 'Content-Type: application/x-vnd.vmware-streamVmdk' %s" % (vmdk2, url))
                result = subprocess.check_output(curl_cmd,stderr=subprocess.STDOUT,shell=True)
                if "Capacity of uploaded disk is larger than request" in result:
                    print result
                    raise 
            except Exception as e:
                print "Yijun:debug:Curl:vmdk2:",curl_cmd
                print "Yijun:debug:Curl:vmdk2:err:",e
                print "Yijun:debug:Curl:vmdk2:path:",vmdk2
            lease.HttpNfcLeaseComplete()
            keepalive_thread.join()
            break

        elif (lease.state == vim.HttpNfcLease.State.error):
            print "[Yijun:debug:]Lease error: " + lease.state
            exit(1)
    connect.Disconnect(si)

def avaDisk(conf):
    si = connect.SmartConnect(host=conf.ucs,user=conf.uUser,pwd=conf.uPasswd,sslContext=sslContext)
#   si = connect.SmartConnect(host=conf.ucs,user=conf.uUser,pwd=conf.uPasswd)
    datacenter_list = si.content.rootFolder.childEntity
    datacenter_obj = datacenter_list[0]
    datastore_list = datacenter_obj.datastoreFolder.childEntity
#   ds = datastore_list[0]
    ds = ""
    for x in datastore_list:
        if conf.dsprefix in x.name:
            ds = x
    try:
        if ds == "":
            print "[Error]No disk prefix %s exist"%(conf.dsprefix)
            ans = raw_input("whether need to continue by ignore this UCS? [y|n]")
            if ans in [Y,y,Yes,YES,yes]:
                return 0
            else:
                sys.exit(1)
    except:
        pass
    freeDisk = ds.summary.freeSpace
    atexit.register(connect.Disconnect, si)
    return freeDisk

def avaMem(conf):
#   container.view[0].GetResourceUsage()  not working
    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
#   si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd)
    content = si.RetrieveContent()
    search_index = content.searchIndex
    host = search_index.FindByDnsName(dnsName=conf.ucs, vmSearch=False)
    perfManager = content.perfManager
    metricId = vim.PerformanceManager.MetricId(counterId=98, instance="*")
#   Amount of host physical memory consumed by a virtual machine, host, or cluster
    startTime = datetime.datetime.now() - datetime.timedelta(hours=10)
    endTime = datetime.datetime.now()
    query = vim.PerformanceManager.QuerySpec(maxSample=1,entity=host,metricId=[metricId],startTime=startTime,endTime=endTime)
    printout = perfManager.QueryPerf(querySpec=[query])
    s =  str(printout)
    pattern = r'(?s)\d*L[^,]'
    value = re.compile(pattern).findall(s)
    if len(value) >= 2:
        print "[Error]:: Consumed Memory Go Error"
        si.disconnect()
        sys.exit(1)
    usedMem = float(value[0].strip().replace("L",""))
    atexit.register(connect.Disconnect, si)

    si = connect.SmartConnect(host=conf.ucs,user=conf.uUser,pwd=conf.uPasswd,sslContext=sslContext)
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)
    host = container.view[0]
    totMem = float(host.hardware.memorySize)
    temp = float(1024)
    totMemKB = totMem/temp

    avaMem = totMemKB-usedMem
    atexit.register(connect.Disconnect, si)

    return avaMem

def existUCS(conf):
    si = connect.SmartConnect(host=conf.ucs,user=conf.uUser,pwd=conf.uPasswd,sslContext=sslContext)
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    num = 0
    for vm in container.view:
        if conf.vmprefix in vm.name:
            num = num +1

    return num

def wait_for_task(task):
    """ wait for a vCenter task to finish """
    task_done = False
    while not task_done:
        if task.info.state == 'success':
            return task.info.result

        if task.info.state == 'error':
            print "there was an error for the task.state"
            task_done = True


def serialClone(conf, ucs,UCSaction,name):
    cloneSourceList = {}
    cloneSourceList[ucs] = ""

    list = range(UCSaction[ucs][0],UCSaction[ucs][1]+1)
    for idx in list:
#       if int(idx) == 1:
#           continue
        newName = conf.vmprefix + "_test" + str(idx)
        if newName == name:
            cloneSourceList[ucs] = newName
            continue
        if cloneSourceList[ucs] != "":
            name = cloneSourceList[ucs]
        else:
            cloneSourceList[ucs] = newName
        print "Debug::YIjun::name==",name
        print "Debug::YIjun::newName==",newName
        clone(conf,ucs,name,newName)




def clone(conf,ucs,name,newName):
#     create content test result show the content from multiprocess is not original content anymore, dont know why
    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)

    template = ""
    for x in container.view:
            if name == x.name:
                template = x
    print "[Info(%s)]::template=%s"%(newName,template)
    try:
        print "[Info(%s)]::template name =%s"%(newName,template.name)
    except:
        print "%s:No clone orig exist! Quit"%(newName)
        sys.exit(1)

    datacenter_list = content.rootFolder.childEntity
    datacenter_obj = ""
    for x in datacenter_list:
        if conf.dcName == x.name:
            datacenter_obj = x
    print "datacenter_obj:",datacenter_obj
    try:
        print "[Info(%s)]::datacenter name =%s"%(newName,datacenter_obj.name)
    except:
        print "%s:No datecenter exist! choose the default one:First one"%(newName)
        datacenter_obj = datacenter_list[0]

    datastore_list = datacenter_obj.datastoreFolder.childEntity
    datastore_obj = ""
    diskName = "hulk"+ucs.split(".")[-1]
    for x in datastore_list:
        if diskName == x.name:
            datastore_obj = x
    print "datastore_obj:",datastore_obj
    try:
        print "[Info(%s)]::datastore name =%s" %(newName,datastore_obj.name)
    except:
        print "%s:No hulk store exist, choose the default one:First one"%(newName)
        datastore_obj = datastore_list[0]

#   if datastore_obj == "":
#       print "No hulk store exist, choose the default one:First one"
#       datastore_obj = datastore_list[0]

    cluster_list = datacenter_obj.hostFolder.childEntity
    cluster_obj = ""
    for x in cluster_list:
        if ucs == x.name:
            cluster_obj = x
    print "cluster_obj:",cluster_obj
    try:
        print "[Info(%s)]::cluster name =%s"%(newName,cluster_obj.name)
    except:
        print "%s:No UCS host exist, choose the default one:First one"%(newName)
        cluster_obj = cluster_list[0]
#   if cluster_obj == "":
#       print "No UCS host exist, choose the default one:First one"
#       cluster_obj = cluster_list[0]

    resource_pool_obj = cluster_obj.resourcePool

    destfolder = datacenter_obj.vmFolder

    relospec = vim.vm.RelocateSpec()
    relospec.datastore = datastore_obj
    relospec.pool = resource_pool_obj

    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec
    clonespec.powerOn = False


    task = template.Clone(folder=destfolder, name=newName, spec=clonespec)
    wait_for_task(task)
    connect.Disconnect(si)

def NewVM(conf):
    global sleepTime
    conf = env(conf)
    rangeVM = rangeVMlist(conf.range)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
    numVM = len(rangeVM)

    UCSlist = conf.UCS.split(",")
    limit = conf.limit
    UCSres = {}
    for i in UCSlist:
        UCSres[i] = limit

    loopCounter = 0
    for ucs in UCSlist:
        conf.ucs = ucs
        print "[Info]Data Fetch for UCS::",ucs
        freeDisk = avaDisk(conf)
        freeDisk = float(freeDisk)
        temp = float(1024*1024*1024)
        freeDisk = freeDisk/temp
        print "[Processing]availabe free Disk in the Host:: %s GB" % (freeDisk)

        freeMem = avaMem(conf)
        temp = float(1024*1024)
        freeMem = freeMem/temp
        print "[Processing]availabe free Memory in the Host:: %s GB" % (freeMem)

        numDisk = freeDisk/90
        numMem = freeMem/16

        num = min(numDisk,numMem)
#       num = min(int(num),limit)
        extNum = existUCS(conf)

        num1 = limit - extNum
        if num1 < 0:
            print "[Warning]existing VM already exceed!!!"
            UCSres[ucs] = 0
        else:

            if limit != 0:
                if num1 < num:
                    num = num1

            UCSres[ucs] = int(num)
            print "[Final]UCS(%s) afforded number of COS VM: %s"%(ucs,UCSres[ucs])
            loopCounter = loopCounter + int(num)

    if loopCounter < numVM:
        print "[Warning]Maximum of COS VM will allowed to reach::%d, but you need::%d" % (loopCounter,numVM)
        ans = raw_input("Whether to continue with the best effort(%d COS VMs)?! [y|n]")
        if ans not in ["Y","y","Yes","YES","yes"]:
            sys.exit(1)

    #load sharing between UCS and speed up the deployment
#   avaNum = numVM/len(UCSlist)
#   extraNum = numVM%len(UCSlist)

    avaNum = numVM/len(UCSlist)
    extraNum = numVM%len(UCSlist)
    UCSaction = {}
    for i in UCSlist:
        UCSaction[i]=0
    num = 0
    scope = list(rangeVM)
    while scope != []:
        for ucs in UCSlist:
            if UCSres[ucs] > UCSaction[ucs]:
                UCSaction[ucs]=UCSaction[ucs]+1
                if scope != []:
                    scope.pop()
                else:
                    break

    index=rangeVM[0]
    for ucs in UCSlist:
        index2 = index+UCSaction[ucs]
        UCSaction[ucs] = (index,index2 -1)
        index = index2
        
    print UCSaction

    for ucs in UCSlist:
        if UCSres[ucs] >= 1:
            conf.ucs = ucs
            name = conf.vmprefix+"_test"+str(UCSaction[ucs][0])
            ImportOVF(conf.ucs,conf.uUser,conf.uPasswd,conf.dsprefix,conf.ovf,name)
            break


    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
#   content=si.content

#"""
#Update Netowork
#
#"""
    content2 = si.RetrieveContent()

    container = content2.viewManager.CreateContainerView(content2.rootFolder, [vim.VirtualMachine], True)
    for x in container.view:
        if x.name == name:
            vm = x
            break

#   vm = container.view[0]
#   vm.config.hardware.device
    device_change = []
    time.sleep(sleepTime)  #dont know why need wait, otherwise error report for the missing property of hardware
    for device in vm.config.hardware.device:
        if device.deviceInfo.label == "Network adapter 1":
            nicspec = vim.vm.device.VirtualDeviceSpec()
            nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
            #   	nicspec.device = vim.vm.device.VirtualE1000e()
            #   	nicspec.device.wakeOnLanEnabled = True
            nicspec.device = device
            nicspec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nicspec.device.backing.deviceName = "VM Network 1"

            c = content2.viewManager.CreateContainerView(content2.rootFolder,[vim.Network],True)
            for idx in c.view:
                if 'VM Network 1' in idx.name:
                    n = idx
            nicspec.device.backing.network = n
            device_change.append(nicspec)

#           config_spec = vim.vm.ConfigSpec(deviceChange=device_change)
#           task = vm.ReconfigVM_Task(config_spec)
#           wait_for_task(task)
        elif device.deviceInfo.label == "Network adapter 2":
            nicspec = vim.vm.device.VirtualDeviceSpec()
            nicspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
            nicspec.device = device
            nicspec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
            nicspec.device.backing.deviceName = "10G-videoVlan"

            c = content2.viewManager.CreateContainerView(content2.rootFolder,[vim.Network],True)
            for idx in c.view:
                if '10G-videoVlan' in idx.name:
                    n = idx
            nicspec.device.backing.network = n
            device_change.append(nicspec)
###10-04
#       elif "Serial" in device.deviceInfo.label and "1" in device.deviceInfo.label:
    Serialspec = vim.vm.device.VirtualDeviceSpec()
    Serialspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    #   	nicspec.device = vim.vm.device.VirtualE1000e()
    #   	nicspec.device.wakeOnLanEnabled = True
    Serialspec.device = vim.vm.device.VirtualSerialPort()
    Serialspec.device.deviceInfo = vim.Description()
#   Serialspec.device.deviceInfo.summary = 'Telnet connection'   #not work, hardcode to "Remote telnnet://:1"
    Serialspec.device.deviceInfo.label = 'Serial port 1'

    Serialspec.device.backing = vim.vm.device.VirtualSerialPort.URIBackingInfo()
    Serialspec.device.backing.serviceURI = "telnet://:%s" % (name.split("_test")[-1])
    Serialspec.device.backing.direction = "server"

    Serialspec.device.connectable = vim.vm.device.VirtualDevice.ConnectInfo()
    Serialspec.device.connectable.startConnected = True
    Serialspec.device.connectable.allowGuestControl = True

    Serialspec.device.yieldOnPoll = True

    device_change.append(Serialspec)

#(vim.vm.device.VirtualSerialPort) {
#     dynamicType = <unset>,
#     dynamicProperty = (vmodl.DynamicProperty) [],
#     key = 9000,
#     deviceInfo = (vim.Description) {
#        dynamicType = <unset>,
#        dynamicProperty = (vmodl.DynamicProperty) [],
#        label = 'Serial port 1',
#        summary = 'Remote telnet://:8301'
#     },
#     backing = (vim.vm.device.VirtualSerialPort.URIBackingInfo) {
#        dynamicType = <unset>,
#        dynamicProperty = (vmodl.DynamicProperty) [],
#        serviceURI = 'telnet://:8301',
#        direction = 'server',
#        proxyURI = <unset>
#     },
#     connectable = (vim.vm.device.VirtualDevice.ConnectInfo) {
#        dynamicType = <unset>,
#        dynamicProperty = (vmodl.DynamicProperty) [],
#        startConnected = true,
#        allowGuestControl = true,
#        connected = false,
#        status = 'untried'
#     },
#     slotInfo = <unset>,
#     controllerKey = 400,
#     unitNumber = 0,
#     yieldOnPoll = true
#  }
###10-04

    print device_change
    config_spec = vim.vm.ConfigSpec(deviceChange=device_change)
    task = vm.ReconfigVM_Task(config_spec)
    print "Debug:YIJUN:before the Clone"
    wait_for_task(task)

    connect.Disconnect(si)
#"""
#Add Serial Port: TBD
#
#   $dev = New-Object VMware.Vim.VirtualDeviceConfigSpec
#   $dev.operation = "add"
#   $dev.device = New-Object VMware.Vim.VirtualSerialPort
#   $dev.device.key = -1
#   $dev.device.backing = New-Object VMware.Vim.VirtualSerialPortURIBackingInfo
#   $dev.device.backing.direction = "server"
#   $dev.device.backing.serviceURI = "telnet://:$prt"
#   $dev.device.connectable = New-Object VMware.Vim.VirtualDeviceConnectInfo
#   $dev.device.connectable.connected = $true
#   $dev.device.connectable.StartConnected = $true
#   $dev.device.yieldOnPoll = $true
#
#   $spec = New-Object VMware.Vim.VirtualMachineConfigSpec
#   $spec.DeviceChange += $dev
#
#   $vm = Get-VM -Name $vmName
#   $vm.ExtensionData.ReconfigVM($spec)
#"""

    jobs = []
    for ucs in UCSlist:
        x = Process(target=serialClone, args=(conf, ucs,UCSaction,name))
        x.start()
        jobs.append(x)

    for x in jobs:
        x.join()


    print "Debug:YIJUN:after the Clone"
    updateSerialPort(None,conf)
#   atexit.register(connect.Disconnect, si)



def UpdateSerialPort(confile,conf=None):
    if confile != None:
        conf = env(confile)
    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
   
    for vm in container.view:
        name = vm.name
        device_change = []
        if conf.vmprefix in name:
            print name
            for device in vm.config.hardware.device:
                if device.deviceInfo.label == "Serial port 1":
                    try:
                        Serialspec = vim.vm.device.VirtualDeviceSpec()
                        Serialspec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
                        Serialspec.device = device
                        Serialspec.device.deviceInfo = vim.Description()
                        Serialspec.device.deviceInfo.summary = "telnet://:%s" % (name.split("_test")[-1])
                        Serialspec.device.deviceInfo.label = 'Serial port 1'
                        Serialspec.device.backing = vim.vm.device.VirtualSerialPort.URIBackingInfo()
                        Serialspec.device.backing.serviceURI = "telnet://:%s" % (name.split("_test")[-1])
                        Serialspec.device.backing.direction = "server"


                        device_change.append(Serialspec)
                    except Exception as e:
                        print e

#   print device_change
                    config_spec = vim.vm.ConfigSpec(deviceChange=device_change)
                    task = vm.ReconfigVM_Task(config_spec)
                    wait_for_task(task)

    connect.Disconnect(si)


def resMatch(conf,rangeVM,name,UCSaction):
    si = connect.SmartConnect(host=name,user=conf.uUser,pwd=conf.uPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    listVM = []
    listUCS = []      
    for x in container.view:
        listUCS.append(x.name)
    for y in rangeVM:
        listVM.append(conf.vmprefix+"_test"+str(y))  

    for item in listVM:
        if item in listUCS:
            UCSaction[name].append(item)

    atexit.register(connect.Disconnect, si)
    return UCSaction

def serialDel(conf, content, ucs,UCSaction):
    list = UCSaction[ucs]
    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in container.view:
        try:
            if vm.name in list:
                if vm.summary.runtime.powerState == "poweredOn":
                    task = vm.PowerOffVM_Task()
                    wait_for_task(task)
                    task2 = vm.Destroy_Task()
                    wait_for_task(task2)
                else:
                    task = vm.Destroy_Task()
                    wait_for_task(task)
        except Exception as e:   #The object has already been deleted or has not been completely created
            print e

        atexit.register(connect.Disconnect, si)

def DelVM(conf):
    conf = env(conf)
    rangeVM = rangeVMlist(conf.range)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
    numVM = len(rangeVM)
    UCSlist = conf.UCS.split(",")
    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction
    atexit.register(connect.Disconnect, si)
    print "Debug::UCSlist:",UCSlist
    jobs = []
    for ucs in UCSaction:
        print ucs
        if ucs not in UCSlist:
            continue
        x = Process(target=serialDel, args=(conf, content, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()



def serialRBT(conf, ucs,UCSaction):
    list = UCSaction[ucs]

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)

#   for vm in container.view:
#       if vm.name in list:
#           task = vm.ResetVM_Task()
#           wait_for_task(task)
#           time.sleep(60)

    for vm in container.view:
        if vm.name in list:
            if vm.summary.runtime.powerState == "poweredOn":
                task = vm.PowerOffVM_Task()
                wait_for_task(task)

    for vm in container.view:
        if vm.name in list:
            if vm.summary.runtime.powerState == "poweredOff":
                task = vm.PowerOnVM_Task()
                wait_for_task(task)
                time.sleep(60)

    atexit.register(connect.Disconnect, si)



def RebootVM(conf):
    conf = env(conf)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
    rangeVM = rangeVMlist(conf.range)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
    numVM = len(rangeVM)
    UCSlist = conf.UCS.split(",")
    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction
    atexit.register(connect.Disconnect, si)

    jobs = []
    for ucs in UCSaction:
        if ucs not in UCSlist:
            continue
        x = Process(target=serialRBT, args=(conf, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()
    




def CloneVM(conf):
    conf = env(conf)
    rangeVM = rangeVMlist(conf.range)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
    numVM = len(rangeVM)

    UCSlist = conf.UCS.split(",")
    limit = conf.limit
    UCSres = {}
    for i in UCSlist:
        UCSres[i] = limit

    loopCounter = 0
    for ucs in UCSlist:
        conf.ucs = ucs
        print "[Info]Data Fetch for UCS::",ucs
        freeDisk = avaDisk(conf)
        freeDisk = float(freeDisk)
        temp = float(1024*1024*1024)
        freeDisk = freeDisk/temp
        print "[Processing]availabe free Disk in the Host:: %s GB" % (freeDisk)

        freeMem = avaMem(conf)
        temp = float(1024*1024)
        freeMem = freeMem/temp
        print "[Processing]availabe free Memory in the Host:: %s GB" % (freeMem)

        numDisk = freeDisk/90
        numMem = freeMem/16

        num = min(numDisk,numMem)
#       num = min(int(num),limit)
        extNum = existUCS(conf)

        num1 = limit - extNum
        if num1 < 0:
            print "[Warning]existing VM already exceed!!!"
            UCSres[ucs] = 0
        else:

            if limit != 0:
                if num1 < num:
                    num = num1

            UCSres[ucs] = int(num)
            print "[Final]UCS(%s) afforded number of COS VM: %s"%(ucs,UCSres[ucs])
            loopCounter = loopCounter + int(num)

    if loopCounter < numVM:
        print "[Warning]Maximum of COS VM will allowed to reach::%d, but you need::%d" % (loopCounter,numVM)
        ans = raw_input("Whether to continue with the best effort(%d COS VMs)?! [y|n]")
        if ans not in ["Y","y","Yes","YES","yes"]:
            sys.exit(1)

    #load sharing between UCS and speed up the deployment
#   avaNum = numVM/len(UCSlist)
#   extraNum = numVM%len(UCSlist)

    avaNum = numVM/len(UCSlist)
    extraNum = numVM%len(UCSlist)
    UCSaction = {}
    for i in UCSlist:
        UCSaction[i]=0
    num = 0
    scope = list(rangeVM)
    while scope != []:
        for ucs in UCSlist:
            if UCSres[ucs] > UCSaction[ucs]:
                UCSaction[ucs]=UCSaction[ucs]+1
                if scope != []:
                    scope.pop()
                else:
                    break

    index=rangeVM[0]
    for ucs in UCSlist:
        index2 = index+UCSaction[ucs]
        UCSaction[ucs] = (index,index2 -1)
        index = index2
        
    print UCSaction

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content

    name = conf.cloneSource
    jobs = []
    for ucs in UCSlist:
        x = Process(target=serialClone, args=(conf, ucs,UCSaction,name))
        x.start()
        jobs.append(x)

    for x in jobs:
        x.join()


    atexit.register(connect.Disconnect, si)


def serialShutdown(conf, ucs,UCSaction):
    list = UCSaction[ucs]
    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)

    for vm in container.view:
        if vm.name in list:
            if vm.summary.runtime.powerState == "poweredOn":
                task = vm.PowerOffVM_Task()
                wait_for_task(task)

    atexit.register(connect.Disconnect, si)

def ShutdownVM(conf):
    conf = env(conf)
    rangeVM = rangeVMlist(conf.range)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
    numVM = len(rangeVM)
    UCSlist = conf.UCS.split(",")
    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction
    atexit.register(connect.Disconnect, si)

    jobs = []
    for ucs in UCSaction:
        if ucs not in UCSlist:
            continue
        x = Process(target=serialShutdown, args=(conf, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()




def serialBootUp(conf, ucs,UCSaction):
    list = UCSaction[ucs]

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)

    for vm in container.view:
        if vm.name in list:
            if vm.summary.runtime.powerState != "poweredOn":
                task = vm.PowerOnVM_Task()
                wait_for_task(task)
                time.sleep(60)

    atexit.register(connect.Disconnect, si)
            

def BootUpVM(conf):
    conf = env(conf)
    rangeVM = rangeVMlist(conf.range)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   if "-" in str(conf.range):
#       rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   else:
#       rangeVM = [int(conf.range)]
    numVM = len(rangeVM)
    UCSlist = conf.UCS.split(",")
    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=conf.vUser,pwd=conf.vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction
    atexit.register(connect.Disconnect, si)
    
    jobs = []
    for ucs in UCSaction:
        if ucs not in UCSlist:
            continue
        x = Process(target=serialBootUp, args=(conf, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()
#   atexit.register(connect.Disconnect, si)


def PowerCycleCrashVM(conf):
    conf = env(conf)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   numVM = len(rangeVM)

    cont = ""
    list = []
    ans = raw_input("Please specify the Crash Files::")
    ans = ans.strip()
    with open(ans,"r") as f:
        cont = f.read()

    tmpList = re.compile(r'(?<=crash:).*').findall(cont)
    for i in tmpList:
        list.append(int(i.strip()))

    rangeVM = list.sort()
    numVM = len(rangeVM)


    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=vUser,pwd=vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction

    jobs = []
    for ucs in UCSaction:
        x = Process(target=serialRBT, args=(conf, content, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()
    atexit.register(connect.Disconnect, si)


def PowerOffCrashVM(conf):
    conf = env(conf)
#   rangeVM = range(int(conf.range.split('-')[0]),int(conf.range.split('-')[1])+1)
#   numVM = len(rangeVM)

    cont = ""
    list = []
    ans = raw_input("Please specify the Crash Files::")
    ans = ans.strip()
    with open(ans,"r") as f:
        cont = f.read()

    tmpList = re.compile(r'(?<=crash:).*').findall(cont)
    for i in tmpList:
        list.append(int(i.strip()))

    rangeVM = list.sort()
    numVM = len(rangeVM)


    UCSaction = {}

    si = connect.SmartConnect(host=conf.vCenter,user=vUser,pwd=vPasswd,sslContext=sslContext)
    content=si.content
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.HostSystem], True)

    for host in container.view:  
        name = host.name
        UCSaction[name] = []
        UCSaction = resMatch(conf,rangeVM,name,UCSaction)
    print "Debug::UCSaction:",UCSaction

    jobs = []
    for ucs in UCSaction:
        x = Process(target=serialShutdown, args=(conf, content, ucs,UCSaction))
        x.start()
        jobs.append(x)


    for x in jobs:
        x.join()
    atexit.register(connect.Disconnect, si)




if __name__ == '__main__':
#   global sleepTime
    usage ="""
example: %prog -f config.yaml [-n seconds]
"""
    parser = optparse.OptionParser(usage)

    parser.add_option("-f", "--File", dest="rConfig",
                      default='Null',action="store",
                      help="the Input Configure file specified by user")
    parser.add_option("-n", "--Time", dest="rSleepSec",
                      default='0',action="store",
                      help="the Input Sleep Time specified by user")
    (options, args) = parser.parse_args()

    argc = len(args)
    if argc != 0:
        parser.error("incorrect number of arguments")
        print usage
    else:
        if options.rConfig != "Null":
          sleepTime=int(options.rSleepSec)
          conf = options.rConfig.strip()
          question = """
What Operation you want to perform::
[1]Create All VMs[Deprecated]
[2]Remove All VMs[Deprecated]
[3]New VMs[V]
[4]Delete VMs[V]
[5]Reboot VMs[V]
[6]Clone VMs[V]
[7]Modify VMs[Deprecated]
[8]Shutdown VMs[V]
[9]BootUP VMs[V]
[10]Power Cycle Crashed VMs[V]
[11]Power off Crashed VMs[V]
[12]Reset Serial Port[V]
*Input Action Number[1|2|3|4|5|6|7|8|9|10|11|12]::"""
          ans = raw_input(question)
          choice = int(ans.strip())
          if choice == 1:
              pass
          elif choice == 2:
              pass
          elif choice == 3:
              ans = raw_input("Whether you want to Continue the operation of New VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  print "****************Notice Begin*********************"
                  print "Remember to run the following Command to Fetch Map btw VM name and Mac::"
                  print "./Mac2Host2.ps1 -vCenterIP 10.94.193.244 -vCenterUser root -vCenterPwd vmware"
                  print "****************Notice Finish*********************"
                  result = NewVM(conf)
                  print "****************Notice Begin*********************"
                  print "Remember to run the following Command to Fetch Map btw VM name and Mac::"
                  print "./Mac2Host2.ps1 -vCenterIP 10.94.193.244 -vCenterUser root -vCenterPwd vmware"
                  print "****************Notice Finish*********************"
      
          elif choice == 4:
              ans = raw_input("Whether you want to Continue the operation of Delete VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = DelVM(conf)
          elif choice == 5:
              ans = raw_input("Whether you want to Continue the operation of Reboot VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = RebootVM(conf)
          elif choice == 6:
              ans = raw_input("Whether you want to Continue the operation of Clone VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = CloneVM(conf)
          elif choice == 7:
              pass
          elif choice == 8:
              ans = raw_input("Whether you want to Continue the operation of Shutdown VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = ShutdownVM(conf)   
          elif choice == 9:
              ans = raw_input("Whether you want to Continue the operation of BootUp VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = BootUpVM(conf)              
          elif choice == 10:
              ans = raw_input("Whether you want to Continue the operation of PowerCycle VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = PowerCycleCrashVM(conf)             
          elif choice == 11:      
              ans = raw_input("Whether you want to Continue the operation of PowerOff Crashed VMs! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = PowerOffCrashVM(conf)  
          elif choice == 12:      
              ans = raw_input("Whether you want to Continue the operation of Reset Serial Ports! [y|n]::")
              if ans in ["Y","y","Yes","yes","YES"]:
                  result = UpdateSerialPort(conf) 
          else:
              print "Incorrect Input::",ans
              sys.exit(1)

          #result = execute(options.Cluster,IPfirst, IPlast)


        else: 
            print usage


