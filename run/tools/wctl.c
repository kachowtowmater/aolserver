/* wctl: drive Win32 dialogs from the shell.
 *   wctl list                     top-level windows + child controls
 *   wctl click <text>             click the first visible button labelled <text> (case-insensitive)
 *   wctl clickh <hwnd>            click a control by handle (for unlabeled AOL icons)
 *   wctl items <hwnd> / select <hwnd> <prefix|#index>   read / pick a combobox entry
 *   wctl settext <class#n> <text> set text of nth child of class in foreground-most dialog
 *   wctl key <vk>                 post WM_KEYDOWN/UP to the topmost visible window */
#include <windows.h>
#include <stdio.h>
#include <string.h>

static const char *want; static HWND found;

static BOOL CALLBACK child_list(HWND h, LPARAM lp) {
    char cls[64], txt[256];
    GetClassNameA(h, cls, sizeof cls); GetWindowTextA(h, txt, sizeof txt);
    printf("    %p %-14s vis=%d en=%d \"%s\"\n", (void *)h, cls, IsWindowVisible(h), IsWindowEnabled(h), txt);
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

int main(int argc, char **argv) {
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
