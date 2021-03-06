#!/usr/bin/env python
#============================================================================
# Copyright (C) Microsoft Corporation, All rights reserved.
#============================================================================

import os
import sys
import imp
import re
import codecs
import shutil
import json
import fileinput
import hashlib
import traceback
import time

protocol = imp.load_source('protocol', '../protocol.py')
nxDSCLog = imp.load_source('nxDSCLog', '../nxDSCLog.py')

LG = nxDSCLog.DSCLog

RESOURCE_MODULE_PATH = '/opt/microsoft/omsconfig/modules/nxOMSWLI/DSCResources/MSFT_nxOMSWLIResource/WLI/'
PLUGIN_RPATH = 'plugins/'
CONF_RPATH = 'conf/'

PLUGIN_DEST_PATH = '/opt/microsoft/omsagent/plugin/'
CONF_DEST_PATH_PREFIX = '/etc/opt/microsoft/omsagent/'
CONF_DEST_PATH_SUFFIX = '/conf/omsagent.d'

BLOCK_SIZE = 8192

class IOMSAgent:
    def restart_oms_agent(self):
        pass

class OMSAgentUtil(IOMSAgent):
    def restart_oms_agent(self, workspaceId):
        wsId = workspaceId
        if wsId is None:
            wsId = ''
        if os.system('sudo /opt/microsoft/omsagent/bin/service_control restart %s' %(wsId)) == 0:
            return True
        else:
            LG().Log('Error', 'Error restarting omsagent for workspace ' + wsId)
            return False

OMS_ACTION = OMSAgentUtil()

class WLISettings:
    workload_name = ""
    ensure = ""
    plugin_loc = ""
    config_cmd = ""
    require_sudo = False

    def __init__(self, settingsDict):
        if 'WorkloadName' in settingsDict:
            self.workload_name = settingsDict['WorkloadName'].encode('ascii', 'ignore')
        if 'Ensure' in settingsDict:
            self.ensure = settingsDict['Ensure'].encode('ascii', 'ignore')
        if 'Plugin' in settingsDict:
            self.plugin_loc = settingsDict['Plugin'].encode('ascii', 'ignore')
        if 'ConfigCommand' in settingsDict:
            self.config_cmd = settingsDict['ConfigCommand'].encode('ascii', 'ignore')
            self.require_sudo = settingsDict["RequireSudo"]

def Set_Marshall(WorkspaceId, Configuration):
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore')
    config_ary = json.loads(Configuration)['WLIConfiguration']
    wli_settings = Get_WLI_Settings(config_ary)
    for ws in wli_settings:
        retval = Set(WorkspaceId, ws)
        if not retval:
            return [-1]
    return [0]

def Test_Marshall(WorkspaceId, Configuration):
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore')
    config_ary = json.loads(Configuration)['WLIConfiguration']
    wli_settings = Get_WLI_Settings(config_ary)
    for ws in wli_settings:
        retval = Test(WorkspaceId, ws)
        if not retval:
            return [-1]
    return [0]

def Get_Marshall(WorkspaceId, Configuration):
    arg_names = list(locals().keys())
    WorkspaceId = WorkspaceId.encode('ascii', 'ignore')
    retval = 0
    local_workloads = Get(WorkspaceId)
    Configuration = protocol.MI_String(str(local_workloads))
    WorkspaceId = protocol.MI_String(WorkspaceId)
    retd = {}
    ld = locals()
    for k in arg_names:
        retd[k] = ld[k]
    return retval, retd

def Get(wid):
    workloads = []
    resource_conf_path = RESOURCE_MODULE_PATH.__add__(CONF_RPATH)
    sub_dirs = []
    dirs = os.listdir(resource_conf_path)
    for sub_dir in dirs:
        if os.path.isdir(os.path.join(resource_conf_path, sub_dir)):
            sub_dirs.append(sub_dir)
    for sub_dir in sub_dirs:
        retval = Check_All_Files(wid, os.path.join(resource_conf_path, sub_dir), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX)
        if retval:
            workloads.append({'WorkloadName': sub_dir, 'Ensure': 'Present'})
        else:
            workloads.append({'WorkloadName': sub_dir, 'Ensure': 'Absent'})
    return workloads

def Get_WLI_Settings(config_array):
    wli_config = []
    for config in config_array:
        wli_setting = WLISettings(config)
        wli_config.append(wli_setting)
    return wli_config

def Set(wid, wli_setting):
    retval = True
    if wli_setting.ensure == 'Present':
        retval &= Update_Plugin_Files(wid, wli_setting.plugin_loc)
        retval &= Update_Conf_Files(wid, wli_setting.workload_name)
    else:
        retval &= Delete_All_Files(RESOURCE_MODULE_PATH.__add__(CONF_RPATH).__add__(wli_setting.workload_name), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX, True)
    retval &= OMS_ACTION.restart_oms_agent(wid)
    return retval
        

def Test(wid, wli_setting):
    retval = True
    if wli_setting.ensure == 'Present':
        retval &= Check_All_Files(wid, RESOURCE_MODULE_PATH.__add__(PLUGIN_RPATH).__add__(wli_setting.plugin_loc), PLUGIN_DEST_PATH)
        retval &= Check_All_Files(wid, RESOURCE_MODULE_PATH.__add__(CONF_RPATH).__add__(wli_setting.workload_name), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX)
    else:
        retval &= not Check_All_Files(wid, RESOURCE_MODULE_PATH.__add__(CONF_RPATH).__add__(wli_setting.workload_name), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX)
    return retval

def Update_Plugin_Files(wid, plugin_loc):
    retval = True
    #replace files
    retval &= Delete_All_Files(RESOURCE_MODULE_PATH.__add__(PLUGIN_RPATH).__add__(plugin_loc), PLUGIN_DEST_PATH)
    retval &= Copy_All_Files(RESOURCE_MODULE_PATH.__add__(PLUGIN_RPATH).__add__(plugin_loc), PLUGIN_DEST_PATH)
    return retval

def Update_Conf_Files(wid, workload_name):
    retval = True
    retval &= Delete_All_Files(RESOURCE_MODULE_PATH.__add__(CONF_RPATH).__add__(workload_name), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX)
    retval &= Copy_All_Files(RESOURCE_MODULE_PATH.__add__(CONF_RPATH).__add__(workload_name), CONF_DEST_PATH_PREFIX + wid + CONF_DEST_PATH_SUFFIX)
    return retval

def Copy_All_Files(src, dest):
    try:
        src_files = os.listdir(src)
        for file_name in src_files:
            full_file_name = os.path.join(src, file_name)
            dest_file_name = os.path.join(dest, file_name)
            if (os.path.isfile(full_file_name)):
                shutil.copy(full_file_name, dest)
                ext = os.path.splitext(dest_file_name)[1]
                if(len(ext) > 0 and ext == '.conf'):
                    for line in fileinput.FileInput(dest_file_name, inplace=True):
                        print(line.replace("%CONF_DIR_WS%", dest))
    except Exception as ex:
        LG().Log('Error', 'copy_all_files failed for src: ' + src + ' dest: ' + dest + ' with exception: ' + str(ex))
        return False
    return True

def Delete_All_Files(src, dest, conf_only=False):
    try:
        src_files = os.listdir(src)
        for file_name in src_files:
            full_file_name = os.path.join(dest, file_name)
            if (os.path.isfile(full_file_name) and not conf_only):
                os.remove(full_file_name)
            elif (os.path.isfile(full_file_name) and conf_only):
                file_ext = os.path.splitext(full_file_name)[1]
                if(len(file_ext) > 0 and file_ext == '.conf'):
                    os.remove(full_file_name)
    except Exception as ex:
        LG().Log('Error', 'delete_all_files failed for src: ' + src + ' dest: ' + dest + ' with exception: ' + str(ex))
        return False
    return True

def Check_All_Files(wid, src, dest):
    try:
        src_files = os.listdir(src)
        for file_name in src_files:
            src_file_path = os.path.join(src, file_name)
            dest_file_path = os.path.join(dest, file_name)
            tmp_file_path = '/tmp/wli_' + wid + '/' + file_name       
            if os.path.isfile(dest_file_path):
                if Compare_Files(wid, dest_file_path, src_file_path, 'md5', tmp_file_path) == -1:
                    if (os.path.isfile(tmp_file_path)):
                        os.remove(tmp_file_path)
                    return False
                else:
                    if (os.path.isfile(tmp_file_path)):
                        os.remove(tmp_file_path)
            else:
                return False
        return True
    except Exception as ex:
        LG().Log('ERROR', 'check_all_files failed for src: ' + src + ' dest: ' + dest + ' with error ' + str(ex))
        return False

def Create_Tmp_Conf_File(wid, conf_file, dest):
    try:
        tmp_dir = '/tmp/wli_' + wid
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)
        file_name = os.path.basename(conf_file)
        LG().Log('INFO', "FILE: " + file_name + " Dir: " + str(os.path.join(tmp_dir, file_name)))
        if (os.path.isfile(conf_file)):
            shutil.copy(conf_file, tmp_dir)
        for line in fileinput.FileInput(os.path.join(tmp_dir, file_name), inplace=True):
            print(line.replace("%CONF_DIR_WS%", os.path.dirname(dest)))
        return True
    except Exception as ex:
        LG().Log('Error', 'create_tmp_conf_file failed for conf: ' + conf_file + ' with exception: ' + str(ex))
        return False

def Compare_Files(wid, DestinationPath, SourcePath, Checksum, TmpPath):
    """
    If the files differ in size, return -1.
    Reading and computing the hash here is done in a block-by-block manner,
    in case the file is quite large.
    """
    src_file_ext = os.path.splitext(SourcePath)[1]
    if(len(src_file_ext) > 0 and src_file_ext == '.conf'):
        if Create_Tmp_Conf_File(wid, SourcePath, DestinationPath):
            SourcePath = TmpPath
    if SourcePath == DestinationPath:  # Files are the same!
        return 0
    stat_dest = StatFile(DestinationPath)
    stat_src = StatFile(SourcePath)
    if stat_src.st_size != stat_dest.st_size:
        return -1
    if Checksum == 'md5':
        src_error = None
        dest_error = None
        src_block = 'loopme'
        dest_block = 'loopme'
        src_file, src_error = opened_bin_w_error(SourcePath, 'rb')
        if src_error:
            LG().Log('Error','Exception opening source file ' + SourcePath
                        + ' Error : ' + str(src_error))
            return -1
        dest_file, dest_error = opened_bin_w_error(DestinationPath, 'rb')
        if dest_error:
            LG().Log('Error','Exception opening destination file ' + DestinationPath
                        + ' Error : ' + str(dest_error))
            src_file.close()
            return -1
        while src_block != '' and dest_block != '':
            src_block = src_file.read(BLOCK_SIZE)
            dest_block = dest_file.read(BLOCK_SIZE)
            hashlib.md5().update(src_block)
            hashlib.md5().update(dest_block)
            if hashlib.md5().hexdigest() != hashlib.md5().hexdigest():
                src_file.close()
                dest_file.close()
                return -1  
        if hashlib.md5().hexdigest() == hashlib.md5().hexdigest():
            src_file.close()
            dest_file.close()
            return 0  
    elif Checksum == 'ctime':
        if stat_src.st_ctime != stat_dest.st_ctime:
            return -1
        else:
            return 0
    elif Checksum == 'mtime':
        if stat_src.st_mtime != stat_dest.st_mtime:
            return -1
        else:
            return 0

def StatFile(path):
    """
    Stat the file, following the symlink.
    """
    d = None
    error = None
    try:
        d = os.stat(path)
    except OSError, error:
        LG().Log('Exception stating file ' + path  + ' Error: '
                    + str(error))
    except IOError, error:
        LG().Log('Exception stating file ' + path  + ' Error: '
                    + str(error))
    return d

def opened_bin_w_error(filename, mode='rb'):
    """
    This context ensures the file is closed.
    """
    try:
        f = open(filename, mode)
    except IOError, error:
        return None, error
    return f, None
    
