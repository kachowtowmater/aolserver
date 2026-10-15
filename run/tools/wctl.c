/* wctl: drive Win32 dialogs from the shell.
 *   wctl list                     top-level windows + child controls
 *   wctl click <text>             click the first visible button labelled <text> (case-insensitive)
 *   wctl clickh <hwnd>            click a control by handle (for unlabeled AOL icons)
 *   wctl items <hwnd> / select <hwnd> <prefix|#index>   read / pick a combobox entry
 *   wctl settext <class#n> <text> set text of nth child of class in foreground-most dialog
 *   wctl key <vk>                 post WM_KEYDOWN/UP to the topmost visible window
 *   wctl close <hwnd>             close a window (AOL child windows go through the MDI client)
 *   wctl closeall                 close every AOL child window (MDI children of the AOL frame)
 *   wctl dismiss                  press OK on every message box (#32770); prints how many
 *   wctl enter <hwnd>             press Enter in a control
 *   wctl clickat <hwnd> <x> <y>   real mouse click at (x,y) inside a window's client area (SendInput)
 *   wctl wheel <hwnd> <x> <y> <n> real mouse-wheel scroll, n notches (negative = down) */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static const char *want; static HWND found;

static BOOL CALLBACK child_list(HWND h, LPARAM lp) {
    char cls[64], txt[256]; RECT r;
    GetClassNameA(h, cls, sizeof cls); GetWindowTextA(h, txt, sizeof txt); GetWindowRect(h, &r);
    printf("    %p %-14s vis=%d en=%d @%ld,%ld \"%s\"\n", (void *)h, cls, IsWindowVisible(h), IsWindowEnabled(h), r.left, r.top, txt);
    return TRUE;
}

static BOOL CALLBACK top_list(HWND h, LPARAM lp) {
    char cls[64], txt[256]; RECT r;
    if (!IsWindowVisible(h)) return TRUE;
    GetClassNameA(h, cls, sizeof cls); GetWindowTextA(h, txt, sizeof txt); GetWindowRect(h, &r);
    printf("%p %-20s \"%s\" [%ld,%ld %ldx%ld]\n", (void *)h, cls, txt, r.left, r.top, r.right - r.left, r.bottom - r.top);
    EnumChildWindows(h, child_list, 0);
    return TRUE;
}

static void strip_amp(const char *s, char *out) { while (*s) { if (*s != '&') *out++ = *s; s++; } *out = 0; }

static BOOL CALLBACK child_find(HWND h, LPARAM lp) {
    char cls[64], txt[256], clean[256];
    if (!IsWindowVisible(h) || !IsWindowEnabled(h)) return TRUE;
    GetClassNameA(h, cls, sizeof cls); GetWindowTextA(h, txt, sizeof txt); strip_amp(txt, clean);
    if (strstr(_strlwr(cls), "button") && !_stricmp(_strlwr(clean), want)) { found = h; return FALSE; }
    return TRUE;
}

static BOOL CALLBACK top_find(HWND h, LPARAM lp) {
    if (!IsWindowVisible(h)) return TRUE;
    EnumChildWindows(h, child_find, 0);
    return found == NULL;
}

static int n_closed;
static BOOL CALLBACK mdi_close(HWND h, LPARAM lp) {
    char cls[64]; GetClassNameA(h, cls, sizeof cls);
    if (!strcmp(cls, "AOL Child") && IsWindowVisible(h)) {
        SendMessageA(GetParent(h), WM_MDIDESTROY, (WPARAM)h, 0); n_closed++;
    }
    return TRUE;
}
static BOOL CALLBACK frame_close(HWND h, LPARAM lp) {
    char cls[64]; GetClassNameA(h, cls, sizeof cls);
    if (!strcmp(cls, "AOL Frame25")) EnumChildWindows(h, mdi_close, 0);
    return TRUE;
}
static BOOL CALLBACK box_ok(HWND h, LPARAM lp) {
    char cls[64]; GetClassNameA(h, cls, sizeof cls);
    if (!strcmp(cls, "#32770") && IsWindowVisible(h)) {
        PostMessageA(h, WM_COMMAND, MAKEWPARAM(IDOK, BN_CLICKED), 0); n_closed++;
    }
    return TRUE;
}

int main(int argc, char **argv) {
    if (argc >= 3 && !strcmp(argv[1], "close")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16); char cls[64]; GetClassNameA(h, cls, sizeof cls);
        if (!strcmp(cls, "AOL Child")) SendMessageA(GetParent(h), WM_MDIDESTROY, (WPARAM)h, 0);
        else PostMessageA(h, WM_CLOSE, 0, 0);
        printf("closed %p\n", (void *)h); return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "closeall")) { EnumWindows(frame_close, 0); printf("closed %d\n", n_closed); return 0; }
    if (argc >= 2 && !strcmp(argv[1], "dismiss")) { EnumWindows(box_ok, 0); printf("dismissed %d\n", n_closed); return 0; }
    if (argc >= 5 && (!strcmp(argv[1], "clickat") || !strcmp(argv[1], "wheel"))) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16);
        POINT pt = { atoi(argv[3]), atoi(argv[4]) }; ClientToScreen(h, &pt);
        SetForegroundWindow(GetAncestor(h, GA_ROOT)); SetCursorPos(pt.x, pt.y); Sleep(100);
        INPUT in[2] = {0}; in[0].type = in[1].type = INPUT_MOUSE;
        if (!strcmp(argv[1], "clickat")) {
            in[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN; in[1].mi.dwFlags = MOUSEEVENTF_LEFTUP; SendInput(2, in, sizeof(INPUT));
        } else {
            in[0].mi.dwFlags = MOUSEEVENTF_WHEEL; in[0].mi.mouseData = (DWORD)(atoi(argv[5]) * WHEEL_DELTA); SendInput(1, in, sizeof(INPUT));
        }
        printf("%s %p at %ld,%ld\n", argv[1], (void *)h, pt.x, pt.y); return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "enter")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16);
        PostMessageA(h, WM_KEYDOWN, VK_RETURN, 0x001C0001); PostMessageA(h, WM_CHAR, '\r', 0x001C0001);
        PostMessageA(h, WM_KEYUP, VK_RETURN, 0xC01C0001); printf("enter %p\n", (void *)h); return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "list")) { EnumWindows(top_list, 0); return 0; }
    if (argc >= 3 && !strcmp(argv[1], "click")) {
        static char w[256]; strip_amp(argv[2], w); want = _strlwr(w);
        EnumWindows(top_find, 0);
        if (!found) { printf("no button matching \"%s\"\n", argv[2]); return 1; }
        char cls[64]; GetClassNameA(found, cls, sizeof cls);
        if (!_stricmp(cls, "Button")) {
            PostMessageA(GetParent(found), WM_COMMAND, MAKEWPARAM(GetDlgCtrlID(found), BN_CLICKED), (LPARAM)found);
        } else {  /* AOL's custom controls only react to real mouse input */
            RECT r; GetClientRect(found, &r);
            LPARAM pt = MAKELPARAM(r.right / 2, r.bottom / 2);
            PostMessageA(found, WM_LBUTTONDOWN, MK_LBUTTON, pt);
            PostMessageA(found, WM_LBUTTONUP, 0, pt);
        }
        printf("clicked %p\n", (void *)found); return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "clickh")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16); RECT r; GetClientRect(h, &r);
        LPARAM pt = MAKELPARAM(r.right / 2, r.bottom / 2);
        PostMessageA(h, WM_LBUTTONDOWN, MK_LBUTTON, pt); PostMessageA(h, WM_LBUTTONUP, 0, pt);
        printf("clicked %p\n", (void *)h); return 0;
    }
    if (argc >= 3 && !strcmp(argv[1], "items")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16);
        LRESULT n = SendMessageA(h, CB_GETCOUNT, 0, 0), cur = SendMessageA(h, CB_GETCURSEL, 0, 0);
        for (LRESULT i = 0; i < n; i++) { char t[256] = ""; SendMessageA(h, CB_GETLBTEXT, i, (LPARAM)t); printf("%c%ld %s\n", i == cur ? '*' : ' ', (long)i, t); }
        return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "select")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16);
        LRESULT i = argv[3][0] == '#' ? atoi(argv[3] + 1)  /* owner-draw lists: pick by index */
                                     : SendMessageA(h, CB_FINDSTRING, (WPARAM)-1, (LPARAM)argv[3]);
        if (i == CB_ERR) { printf("no item \"%s\"\n", argv[3]); return 1; }
        SendMessageA(h, CB_SETCURSEL, i, 0);
        SendMessageA(GetParent(h), WM_COMMAND, MAKEWPARAM(GetDlgCtrlID(h), CBN_SELCHANGE), (LPARAM)h);
        printf("selected %ld\n", (long)i); return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "settext")) {
        HWND h = (HWND)(ULONG_PTR)strtoull(argv[2], NULL, 16);
        SendMessageA(h, WM_SETTEXT, 0, (LPARAM)argv[3]); printf("set\n"); return 0;
    }
    fprintf(stderr, "usage: wctl list | click <text> | settext <hwnd> <text>\n"); return 2;
}
