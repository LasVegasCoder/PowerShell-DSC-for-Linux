#!/usr/bin/python
from imp            import load_source
from os.path        import dirname, isfile, join, realpath
from subprocess     import PIPE, Popen
from sys            import argv, exc_info, exit, version_info
from traceback      import format_exc

pathToCurrentScript = realpath(__file__)
pathToCommonScriptsFolder = dirname(pathToCurrentScript)

helperLibPath = join(pathToCommonScriptsFolder, 'helperlib.py')
helperlib = load_source('helperlib', helperLibPath)

operationStatusUtilityPath = join(pathToCommonScriptsFolder, 'OperationStatusUtility.py')
operationStatusUtility = load_source('operationStatusUtility', operationStatusUtilityPath)

operation = 'SetLCM'

def usage():
    print("Usage:")
    print("    " + argv[0] + " -configurationmof FILE")
    operationStatusUtility.write_failure_to_status_file_no_log(operation, 'Incorrect parameters to SetDscLocalConfigurationManager.py: ' + str(argv))
    exit(1)

def main(args):
    try:
        apply_meta_config(args)
    except SystemExit:
        exit(exc_info()[1])
    except Exception:
        # Python 2.4-2.7 and 2.6-3 recognize different formats for exceptions. This methods works in all versions.
        formattedExceptionMessage = format_exc()
        operationStatusUtility.write_failure_to_status_file_no_log(operation, 'Python exception raised from SetDscLocalConfigurationManager.py: ' + formattedExceptionMessage)
        raise

def apply_meta_config(args):
    if len(args) != 3:
        usage()

    if args[1].lower() != '-configurationmof':
        usage()

    if (not isfile(args[2])):
        errorMessage = 'The provided configurationmof file does not exist: ' + str(args[2])
        print(errorMessage)
        operationStatusUtility.write_failure_to_status_file_no_log(operation, 'Incorrect parameters to SetDscLocalConfigurationManager.py: ' + errorMessage)
        exit(1)

    fileHandle = open(args[2], 'r')
    try:
        fileContent = fileHandle.read()
        outtokens = []
        for char in fileContent:
            outtokens.append(str(ord(char)))

        omicli_path = join(helperlib.CONFIG_BINDIR, 'omicli')

        parameters = []
        parameters.append(omicli_path)
        parameters.append("iv")
        parameters.append(helperlib.DSC_NAMESPACE)
        parameters.append("{")
        parameters.append("MSFT_DSCLocalConfigurationManager")
        parameters.append("}")
        parameters.append("SendMetaConfigurationApply")
        parameters.append("{")
        parameters.append("ConfigurationData")
        parameters.append("[")
        # Insert configurationmof data here
        for token in outtokens:
            parameters.append(token)
        parameters.append("]")
        parameters.append("}")

        # Save the starting timestamp without milliseconds
        startDateTime = operationStatusUtility.get_current_time_no_ms()

        # Apply the metaconfig
        process = Popen(parameters, stdout = PIPE, stderr = PIPE, close_fds = True)
        exit_code = process.wait()
        stdout, stderr = process.communicate()

        print(stdout)

        # Python 3 returns an empty byte array into stderr on success
        if stderr == '' or (version_info >= (3, 0) and stderr.decode(encoding = 'UTF-8') == ''):
            operationStatusUtility.write_success_to_status_file(operation)
            print("Successfully applied metaconfig.")
        else:
            operationStatusUtility.write_failure_to_status_file(operation, startDateTime, stderr)
            print(stderr)

        if ((exit_code != 0) or (stderr)):
            exit(1)
    finally:
        fileHandle.close()

if __name__ == "__main__":
    main(argv)
