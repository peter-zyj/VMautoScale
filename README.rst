<<<<<<< HEAD
=====
Usage
=====

VM candidate creation::

    [powershell] ./COStemplate6-centos6.ps1 -build 3.15.0-b296 -ver virt

========
Required
========

VMware vSphere API Python Bindings

installation::

    pip install pyvmomi

================
Setting/Execution
================

1. Prepare the VMCandidate creation by define the parameters within the powershell scripts::

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

2. Execute the powershell scripts to create the candidate::

    ./COStemplate6-centos6.ps1 -build 3.15.0-b296 -ver virt

3. Then a Folder named by "ovfDir" will be created under the same path as pwshell scripts::

    [root@JMETER ovfDir]# tree -A
    .
    +-- COStmp3.14.2-b19virt
    |   +-- COStmp3.14.2-b19virt_disk0.vmdk
    |   +-- COStmp3.14.2-b19virt_disk1.vmdk
    |   +-- COStmp3.14.2-b19virt.mf
    |   +-- COStmp3.14.2-b19virt.ovf
    +-- COStmp3.15.0-b296virt
    |   +-- back.ovf
    |   +-- COStmp3.15.0-b296virt_disk0.vmdk
    |   +-- COStmp3.15.0-b296virt_disk1.vmdk
    |   +-- COStmp3.15.0-b296virt.mf
    |   +-- COStmp3.15.0-b296virt.ovf
    +-- COStmp4.1.0-b42virt
    |   +-- COStmp4.1.0-b42virt_disk0.vmdk
    |   +-- COStmp4.1.0-b42virt_disk1.vmdk
    |   +-- COStmp4.1.0-b42virt.mf
    |   +-- COStmp4.1.0-b42virt.ovf
    +-- COStmp4.1.0-b43virt
        +-- COStmp4.1.0-b43virt-disk1.vmdk
        +-- COStmp4.1.0-b43virt-disk2.vmdk
        +-- COStmp4.1.0-b43virt.mf
        +-- COStmp4.1.0-b43virt.ovf 

4. Specify the VM candidate path in the config.yaml:: 

    vCenter: 10.94.193.186
    vUser: root
    vPasswd: Vmware123!
    UCS: 10.94.153.80,10.94.153.81,10.94.153.82
    uUser: root
    uPasswd: rootroot
    ovf: the_absolute_path_to/ovfDir/COStmp3.15.0-b296virt/COStmp3.15.0-b296virt.ovf
    range: 1-60
    limit: 30
    crashFile: ./crashFile_94_244
    dsprefix: hulk
    vmprefix: Lindon1
    dcName: LindonScaleCOS
    cloneSource:


5. Execute the Scale Auto Scripts::

    python vmAutoScale.py -f config.yaml
    

    


=======
========
Required
========
VMware vSphere API Python Bindings
installation::
    pip install pyvmomi
>>>>>>> origin/master
