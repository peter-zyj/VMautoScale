#for Centos6 COS image
#release 6-1
#add telnet for VM
#bug fix
param(
   [string]$ver="orig-full",
   [Parameter(Mandatory=$true)][string]$build,
   [string]$user = "root",
   [string]$password = "rootroot",
   [string]$server = "10.94.153.84",
   [string]$disk = "hulk84",
   [string]$vmm = "COStmp",
   [string]$vServer = "10.94.193.186",
   [string]$vUser = "root",
   [string]$vPassword = "Vmware123!"
   )

$build = $build.trim()
$ver = $ver.trim()
$vmm = $vmm+$build+$ver

#status1: not found;
#status2: found and on;
#status3: found and off;
Get-Module -ListAvailable PowerCLI* | Import-Module
Connect-VIServer -Server $server -Protocol https -Username $user -Password $password
$status = ((get-vm -name $vmm).PowerState | out-string).trim()
Disconnect-VIServer -Confirm:$false
if($status -eq "")
{
   $res = Read-Host "!!!!!!!This is the action of NewCreation!!!!!!!, Need to Continue?[y/n]"
   if($res -eq "y"){
    #Fetch the build and rpm package from build server
      #scp root@172.22.68.184:/auto/cds-build/release_builds/usage1.txt .
         if ($build.contains("-")) {
            $image = "cos"+"_"+$build 
            $dir = $build.split('-')[0]
        }else{
            $tmp = $build -replace "\.",""
            $image = "cos"+"_"+$tmp+"_"+"last"
            $dir = $build
        }

      $imageName = $image+".iso"

      if(!$ver.contains("orig")){$version = "cserver-"+$ver+"*rpm"}
      $rpmDir =  "./$imageName"+"_rpm"
      mkdir $rpmDir

      
      if(!$ver.contains("orig")){$verName = $build+"-"+$ver+".rpm"}


      if (!(Test-Path -Path "./$imageName"))
      {scp root@172.22.68.184:/auto/cds-build/release_builds/$dir/$image/target/cos_full*iso $imageName}

      if (!(Test-Path -Path "./$rpmDir/$verName"))
      {if(!$ver.contains("orig")){scp root@172.22.68.184:/auto/cds-build/release_builds/$dir/$image/target/$version ./$rpmDir/$verName}}

      #upload the build and rpm package to UCS
      $isoImage = ($verName -replace "\.","_") + ".iso"
      Try{
      if(!$ver.contains("orig")){genisoimage -o $isoImage ./$rpmDir}
      }
      Catch{
         "!!!!!!!!!!!!!No linux tool genisoimage!!!!!!!!!!!"
      }
      $diskDan = '"'+$disk+'"'
      $diskDan = $diskDan -replace '\(','\('
      $diskDan = $diskDan -replace '\)','\)'
      $diskDan = $diskDan -replace ' ','\ '
      "!!!!!!!!!!!!!!$diskDan!!!!!!!!!!!"
      $cmd1 = "scp ./$imageName root@$server"+":/vmfs/volumes/$diskDan/."
      $cmd1
      if(!$ver.contains("orig")){$cmd2 = "scp ./$isoImage root@$server"+":/vmfs/volumes/$diskDan/."}

      iex $cmd1

      $cmd2
      if(!$ver.contains("orig")){iex $cmd2}

      $rmFile = ls | grep cos_*iso
      
#  rm -rf $rmFile
#  rm -rf ./rpm

      #create/start VM

      Connect-VIServer -Server $server -Protocol https -Username $user -Password $password

      New-VM -name $vmm -DiskGB 60 -memoryGB 16 -StorageFormat EagerZeroedThick -NumCpu 4 -GuestId centos64Guest -Datastore $disk

      Disconnect-VIServer -Confirm:$false


      Connect-VIServer -Server $vServer -Protocol https -Username $vUser -Password $vPassword
      Get-ScsiController -VM $vmm | Set-ScsiController -BusSharingMode NoSharing
      Get-ScsiController -VM $vmm | Set-ScsiController -Type VirtualLsiLogicSAS
      Try{

         $adp1 = get-networkAdapter $vmm -Name "Network adapter 1"
         get-vm $vmm | Get-NetworkAdapter -Name $adp1 | Set-NetworkAdapter -NetworkName "VM Network 1" -Type e1000 -Confirm:$false
         New-NetworkAdapter -VM $vmm -NetworkName "10G-videoVlan" -WakeOnLan -StartConnected -Type e1000
      }Catch{
         New-NetworkAdapter -VM $vmm -NetworkName "VM Network 1" -WakeOnLan -StartConnected -Type e1000
         New-NetworkAdapter -VM $vmm -NetworkName "10G-videoVlan" -WakeOnLan -StartConnected -Type e1000
      }


      $dev = New-Object VMware.Vim.VirtualDeviceConfigSpec
      $dev.FileOperation = "create" 
      $dev.Operation = "add"
      $dev.Device = New-Object VMware.Vim.VirtualDisk 
      $dev.Device.backing = New-Object VMware.Vim.VirtualDiskFlatVer2BackingInfo 
      $dev.Device.backing.Datastore = (Get-Datastore -Name $disk).Extensiondata.MoRef  
      $dev.Device.backing.DiskMode = "persistent"
      $tmp = "[datastore] /vmname/vmname_1.vmdk"
      $tmp = $tmp -replace "datastore","$disk"
      $tmp = $tmp -replace "vmname","$vmm"
      $dev.Device.Backing.FileName = $tmp
      $dev.Device.backing.ThinProvisioned = $true
      $dev.Device.CapacityInKb = (30*1GB) / 1KB 
      $dev.Device.ControllerKey = 200 
      $dev.Device.UnitNumber = -1
      $spec = New-Object VMware.Vim.VirtualMachineConfigSpec 
      $spec.deviceChange += $dev  
      $vm = get-vm -name $vmm
      $vm.ExtensionData.ReconfigVM($spec) 
#!6-1
      $dev = New-Object VMware.Vim.VirtualDeviceConfigSpec
      $dev.operation = "add"
      $dev.device = New-Object VMware.Vim.VirtualSerialPort
      $dev.device.key = -1
      $dev.device.backing = New-Object VMware.Vim.VirtualSerialPortURIBackingInfo
      $dev.device.backing.direction = "server"
      $dev.device.backing.serviceURI = "telnet://:xxx"
      $dev.device.connectable = New-Object VMware.Vim.VirtualDeviceConnectInfo
      $dev.device.connectable.connected = $true
      $dev.device.connectable.StartConnected = $true
      $dev.device.yieldOnPoll = $true

      $spec = New-Object VMware.Vim.VirtualMachineConfigSpec
      $spec.DeviceChange += $dev

      $vm = Get-VM -Name $vmm
      $vm.ExtensionData.ReconfigVM($spec)
#~6-1
      $iso = "[datastore] isoName"
      $iso = $iso -replace "datastore","$disk"
      $iso = $iso -replace "isoName","$imageName"
      New-CDDrive -VM $vmm -Confirm:$false
      Get-VM $vmm | Get-CDDrive | Set-CDDrive -IsoPath $iso -StartConnected $true -Confirm:$false
      $value = "5000"
      $vm = Get-VM $vmm | Get-View
      $vmConfigSpec = New-Object VMware.Vim.VirtualMachineConfigSpec
      $vmConfigSpec.BootOptions = New-Object VMware.Vim.VirtualMachineBootOptions
      $vmConfigSpec.BootOptions.BootDelay = $value
      $vm.ReconfigVM_Task($vmConfigSpec)

      Start-vm -vm $vmm

      Disconnect-VIServer -Confirm:$false

      exit
   }
 
}

if ($status -eq "PoweredOff") {
      #export
      $res = Read-Host "!!!!!!!This is the action of Export!!!!!!!, Need to Continue?[y/n]"
      if ($res -eq "y") {
         $ovfDir = "./ovfDir"
         mkdir $ovfDir
         cd  $ovfDir
         Get-Module -ListAvailable PowerCLI* | Import-Module
         Connect-VIServer -Server $server -Protocol https -Username $user -Password $password
         $cd = Get-CDDrive -VM $vmm
         Remove-CDDrive -CD $cd -Confirm:$false
         Get-VM -Name "$vmm" | Export-VApp -Destination "." -Format Ovf
         Disconnect-VIServer -Confirm:$false
      }

      exit
}else{

   if ($status -eq "PoweredOn") {
         #reboot UCS and change the boot order
         $res = Read-Host "!!!!!!!This is the action of Reboot!!!!!!!, Need to Continue?[y/n]"
         if ($res -eq "y") {
            Get-Module -ListAvailable PowerCLI* | Import-Module
            Connect-VIServer -Server $server -Protocol https -Username $user -Password $password
            Stop-VM $vmm -confirm:$false

            $VMName = get-vm "$vmm" | get-view
            $ide = ($VMName.Config.Hardware.Device | ?{$_.DeviceInfo.Label -eq "Hard Disk 1"}).Key
            $scsi = ($VMName.Config.Hardware.Device | ?{$_.DeviceInfo.Label -eq "Hard Disk 2"}).Key
            $ideboot = New-Object -TypeName VMware.Vim.VirtualMachineBootOptionsBootableDiskDevice -Property @{"DeviceKey" = $ide}        
            $scsiboot = New-Object -TypeName VMware.Vim.VirtualMachineBootOptionsBootableDiskDevice -Property @{"DeviceKey" = $scsi}             
            $spec = New-Object VMware.Vim.VirtualMachineConfigSpec -Property @{"BootOptions" = New-Object VMware.Vim.VirtualMachineBootOptions -Property @{BootOrder = $ideboot,$scsiboot}} 

            $verName = $build+"-"+$ver+".rpm"
            $verName = ($verName -replace "\.","_") + ".iso"
            $iso = "[datastore] isoName"
            $iso = $iso -replace "datastore","$disk"
            $iso = $iso -replace "isoName","$verName"
            Get-VM $vmm | Get-CDDrive | Set-CDDrive -IsoPath $iso -StartConnected $true -Confirm:$false

            $value = "5000"
            $vm = Get-VM $vmm | Get-View
            $vmConfigSpec = New-Object VMware.Vim.VirtualMachineConfigSpec
            $vmConfigSpec.BootOptions = New-Object VMware.Vim.VirtualMachineBootOptions
            $vmConfigSpec.BootOptions.BootDelay = $value
            $vm.ReconfigVM_Task($vmConfigSpec)
            Start-vm -vm $vmm
            Disconnect-VIServer -Confirm:$false
         }
      
         exit
   }else{
      "Error status ::$status, Quit!!!"
      exit
   }
}

#connect candidate and trigger the inital scripts within the candidate
#  @1.copy the following files from the "new" folder to each location
#  1./etc/sysconfig/network /etc/sysconfig/network
#  2./etc/sysconfig/network-scripts/ifcfg-eth0
#  3./etc/hosts /etc/hosts
#  4./etc/ntp.conf
#  5./etc/cassandra/conf/cassandra.yaml
#  6./etc/cosd.conf
#  7./arroyo/test/setupfile
#  8./arroyo/test/SubnetTable
#  9./arroyo/test/RemoteServers
#  @2 .clean all Mac address in 70.....net file for centos6
#     mount /dev/cdrom /mnt/cdrom
#     rpm -ivh /mn t/cdrom/*.rpm
#  @3. rpm installation
#  @4. shutdown -h now


#export ovf

#delete VM



