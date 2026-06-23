#include <stdlib.h>
#include <stdio.h>
#ifdef SAPonNT
#include <windows.h>
#else
#include <unistd.h>
#endif

#include "sapnwrfc.h"

void RfcSleep(unsigned milliSec)
{

#ifdef SAPonNT
    Sleep((DWORD)(milliSec));
#else
    const unsigned int sec = static_cast<unsigned>(milliSec / 1000);
    const unsigned int usec = static_cast<unsigned>(1000 * (milliSec % 1000));
    if (sec)
        sleep(sec);
    if (usec)
        usleep(usec);
#endif
}


static int running = 1;

void errorHandling(const SAP_UC* description, RFC_ERROR_INFO* errorInfo)
{
    printfU(cU("%s : (%d) %s\n"), description, errorInfo->code, errorInfo->message);
    exit(1);
}

void loadCryptolib(const SAP_UC* const pathTolib)
{
    RFC_ERROR_INFO errorInfo;
    RFC_RC rc = RfcLoadCryptoLibrary(pathTolib, &errorInfo);
    if (rc != RFC_OK)
        errorHandling(cU("Could not load cryptolib"), &errorInfo);
}

void installFunctionModules(void)
{
 /* install your modules */
}

int mainU(int argc, SAP_UC** argv)
{
    RFC_RC rc = RFC_OK;
    RFC_ERROR_INFO errorInfo;
    if (argc > 1)
        loadCryptolib(argv[1]);

    RFC_CONNECTION_PARAMETER loginParams[1];
    // sapnwrfc.ini content
    // DEFAULT
    // TLS_SAPCRYPTOLIB=\absolute\path\to\sapcrypto.dll //libsapcrypto.so
    // DEST=SERVER_SAMPLE
    // WSPORT=44318
    // USE_TLS=1
    // TLS_SERVER_PSE=\absolute\path\to\my.pse
    // REG_COUNT=1
    // LANG=EN
    // TLS_SERVER_PARTNER_AUTH=REQUEST
    loginParams[0].name = cU("DEST"); loginParams[0].value = cU("SERVER_SAMPLE");

    installFunctionModules();

    RFC_SERVER_HANDLE serverHandle = RfcCreateServer(loginParams, 1, &errorInfo);

    printfU(cU("Starting to listen...\n\n"));
    rc = RfcLaunchServer(serverHandle, &errorInfo);
    if (rc != RFC_OK)
        errorHandling(cU("Error launching server"), &errorInfo);

    while (running != 0)
    {
        RfcSleep(1000 * 60);
        RFC_SERVER_MONITOR_DATA* monitor = NULL;
        unsigned numberOfConnections = 0;
        rc = RfcGetServerConnectionMonitorData(serverHandle, &numberOfConnections, &monitor, &errorInfo);
        if (rc != RFC_OK)
            errorHandling(cU("Error creating the server monitor"), &errorInfo);

        printfU(cU("Currently %d connections are estabished\n"), numberOfConnections);
        for (unsigned i = 0; i < numberOfConnections; ++i)
        {
            if (monitor[i].isActive)
            {
                printfU(cU("Connection with convID %s is currently processing module %s\n"), monitor[i].clientInfo->cpicConvId, monitor[i].functionModuleName);
            }
            else
            {
                printfU(cU("Connection with convID %s last active at %") SAP_Flld cU("\n"), monitor[i].clientInfo->cpicConvId, monitor[i].lastActivity);
            }
        }

        RfcDestroyServerConnectionMonitorData(numberOfConnections, monitor, &errorInfo);
    }

    rc = RfcShutdownServer(serverHandle, 0, &errorInfo);
    if (rc != RFC_OK)
        errorHandling(cU("Error shutting down server"), &errorInfo);

    RfcDestroyServer(serverHandle, &errorInfo);

    return 0;
}
