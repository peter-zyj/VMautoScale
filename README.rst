=====
Usage
=====

VM candidate creation::
    [powershell] ./COStemplate6-centos6.ps1 -build 3.15.0-b296 -ver virt

VM scale Automation(based on the VM candidate)::
    python vmAutoScale.py -f config.yaml [-n seconds]
