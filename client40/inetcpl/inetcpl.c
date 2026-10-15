/* Stand-in inetcpl.cpl for AOL 4.0 under Wine.
 * AOL's WWW preferences (form 32-4652) asks inetcpl.cpl for Internet Explorer's property
 * pages (AddInternetPropertySheetsEx).  Wine's inetcpl doesn't implement it and aborts the
 * whole client.  Placed in the AOL folder, this one answers "no pages" so the window opens. */
#include <windows.h>
#include <prsht.h>

HRESULT WINAPI AddInternetPropertySheetsEx(LPFNADDPROPSHEETPAGE add, LPARAM lparam, PUINT counter,
                                           LPFNPSPCALLBACK callback, LPVOID ieaks)
{
    if (counter) *counter = 0;
    return S_OK;
}

HRESULT WINAPI AddInternetPropertySheets(LPFNADDPROPSHEETPAGE add, LPARAM lparam, PUINT counter,
                                         LPFNPSPCALLBACK callback)
{
    if (counter) *counter = 0;
    return S_OK;
}

LONG WINAPI CPlApplet(HWND hwnd, UINT msg, LPARAM l1, LPARAM l2) { return 0; }

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved) { return TRUE; }
