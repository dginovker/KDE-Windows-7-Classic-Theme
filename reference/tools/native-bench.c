#define _WIN32_WINNT 0x0601
#define _UNICODE
#include <windows.h>
#include <commctrl.h>
#include <uxtheme.h>
#include <shellapi.h>
#include <stdarg.h>
#include <stddef.h>

static HFONT ui_font;
static HANDLE metadata;
static wchar_t output[MAX_PATH];

static void fail(const wchar_t *message) {
    MessageBoxW(NULL, message, L"Windows 7 reference collector failed", MB_OK | MB_ICONERROR);
    ExitProcess(1);
}
static void path(wchar_t *dest, const wchar_t *name) {
    if(lstrlenW(output)+lstrlenW(name)+2>=MAX_PATH)fail(L"Output path is too long");
    wsprintfW(dest,L"%s\\%s",output,name);
}
static void record(const char *format,...) {
    char line[1024];va_list args;va_start(args,format);wvsprintfA(line,format,args);va_end(args);
    DWORD size=(DWORD)lstrlenA(line),written;
    if(!WriteFile(metadata,line,size,&written,NULL)||written!=size)fail(L"Metadata write failed");
}
void *memset(void *dest,int value,size_t size) {
    volatile unsigned char *p=dest;while(size--)*p++=(unsigned char)value;return dest;
}
void *memcpy(void *dest,const void *source,size_t size) {
    unsigned char *p=dest;const unsigned char *s=source;while(size--)*p++=*s++;return dest;
}
static void font_record(const char *name, LOGFONTW *font) {
    char face[256];
    if (!WideCharToMultiByte(CP_UTF8, 0, font->lfFaceName, -1, face, sizeof(face), NULL, NULL)) fail(L"Font name conversion failed");
    record("font,%s,%s,height=%ld;weight=%ld;quality=%u\n", name, face, font->lfHeight, font->lfWeight, font->lfQuality);
    HFONT selected = CreateFontIndirectW(font);
    HDC dc = CreateCompatibleDC(NULL);
    HGDIOBJ old = SelectObject(dc, selected);
    DWORD size = GetFontData(dc, 0, 0, NULL, 0);
    if (size == GDI_ERROR) fail(L"Selected font is not exportable as TrueType data");
    void *bytes = HeapAlloc(GetProcessHeap(),0,size);
    if (!bytes || GetFontData(dc, 0, 0, bytes, size) != size) fail(L"Could not read selected font data");
    wchar_t file[MAX_PATH], suffix[80];
    wsprintfW(suffix,L"private-font-%hs.ttf",name);
    path(file, suffix);
    HANDLE f=CreateFileW(file,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);DWORD written;
    if(f==INVALID_HANDLE_VALUE||!WriteFile(f,bytes,size,&written,NULL)||written!=size||!FlushFileBuffers(f)||!CloseHandle(f))fail(L"Could not save private font data");
    HeapFree(GetProcessHeap(),0,bytes);
    SelectObject(dc, old); DeleteObject(selected); DeleteDC(dc);
}
static void export_metadata(void) {
    OSVERSIONINFOW version = {0}; version.dwOSVersionInfoSize=sizeof(version);
    if (!GetVersionExW(&version) || version.dwMajorVersion != 6 || version.dwMinorVersion != 1) fail(L"This collector requires genuine Windows 7 (version 6.1)");
    if (IsThemeActive()) fail(L"Apply Windows Classic before running the collector");
    HDC screen = GetDC(NULL);
    int dpi = GetDeviceCaps(screen, LOGPIXELSX);
    ReleaseDC(NULL, screen);
    if (dpi != 96) fail(L"Set display scaling to 100 percent (96 DPI) before collecting");
    wchar_t file[MAX_PATH]; path(file, L"native-metrics.csv");
    metadata=CreateFileW(file,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
    if(metadata==INVALID_HANDLE_VALUE)fail(L"Cannot create metadata file");
    record("category,name,value,detail\nos,version,6.1.%lu,Windows 7\nscreen,dpi,%d,pixels per inch\n", version.dwBuildNumber, dpi);
    const struct { const char *name; int id; } colors[] = {
        {"Background",COLOR_BACKGROUND},{"ButtonFace",COLOR_BTNFACE},{"ButtonShadow",COLOR_BTNSHADOW},
        {"ButtonHighlight",COLOR_BTNHIGHLIGHT},{"ButtonDarkShadow",COLOR_3DDKSHADOW},{"ButtonLight",COLOR_3DLIGHT},
        {"Window",COLOR_WINDOW},{"WindowText",COLOR_WINDOWTEXT},{"ButtonText",COLOR_BTNTEXT},{"Menu",COLOR_MENU},{"MenuText",COLOR_MENUTEXT},
        {"Highlight",COLOR_HIGHLIGHT},{"HighlightText",COLOR_HIGHLIGHTTEXT},{"ActiveCaption",COLOR_ACTIVECAPTION},
        {"InactiveCaption",COLOR_INACTIVECAPTION},{"CaptionText",COLOR_CAPTIONTEXT},{"InactiveCaptionText",COLOR_INACTIVECAPTIONTEXT},
        {"GradientActiveCaption",COLOR_GRADIENTACTIVECAPTION},{"GradientInactiveCaption",COLOR_GRADIENTINACTIVECAPTION},
        {"InfoBackground",COLOR_INFOBK},{"InfoText",COLOR_INFOTEXT},{"GrayText",COLOR_GRAYTEXT},{"HotLight",COLOR_HOTLIGHT}
    };
    for (unsigned i=0; i<sizeof(colors)/sizeof(colors[0]); i++) {
        COLORREF c = GetSysColor(colors[i].id);
        record("color,%s,#%02X%02X%02X,%d\n",colors[i].name,GetRValue(c),GetGValue(c),GetBValue(c),colors[i].id);
    }
    const struct { const char *name; int id; } metrics[] = {
        {"ScreenWidth",SM_CXSCREEN},{"ScreenHeight",SM_CYSCREEN},{"CaptionHeight",SM_CYCAPTION},
        {"SmallCaptionHeight",SM_CYSMCAPTION},{"MenuHeight",SM_CYMENU},{"CaptionButtonWidth",SM_CXSIZE},
        {"CaptionButtonHeight",SM_CYSIZE},{"FrameWidth",SM_CXSIZEFRAME},{"FrameHeight",SM_CYSIZEFRAME},
        {"PaddedBorder",SM_CXPADDEDBORDER},{"BorderWidth",SM_CXBORDER},{"EdgeWidth",SM_CXEDGE},
        {"ScrollWidth",SM_CXVSCROLL},{"ScrollHeight",SM_CYHSCROLL},{"SmallIconWidth",SM_CXSMICON},{"IconWidth",SM_CXICON}
    };
    for(unsigned i=0;i<sizeof(metrics)/sizeof(metrics[0]);i++)record("metric,%s,%d,pixels\n",metrics[i].name,GetSystemMetrics(metrics[i].id));
    NONCLIENTMETRICSW ncm = {0}; ncm.cbSize=sizeof(ncm);
    if (!SystemParametersInfoW(SPI_GETNONCLIENTMETRICS,sizeof(ncm),&ncm,0)) fail(L"Cannot read non-client metrics");
    font_record("Caption",&ncm.lfCaptionFont); font_record("Menu",&ncm.lfMenuFont);
    font_record("Message",&ncm.lfMessageFont); font_record("Status",&ncm.lfStatusFont);
    LOGFONTW icon_font;
    if (!SystemParametersInfoW(SPI_GETICONTITLELOGFONT,sizeof(icon_font),&icon_font,0)) fail(L"Cannot read icon font");
    font_record("Icon",&icon_font);
    BOOL smoothing; UINT smoothing_type;
    if (!SystemParametersInfoW(SPI_GETFONTSMOOTHING,0,&smoothing,0) || !SystemParametersInfoW(SPI_GETFONTSMOOTHINGTYPE,0,&smoothing_type,0)) fail(L"Cannot read font smoothing settings");
    UINT contrast;
    if (!SystemParametersInfoW(SPI_GETFONTSMOOTHINGCONTRAST,0,&contrast,0)) fail(L"Cannot read ClearType contrast");
    record("font-setting,Smoothing,%d,bool\nfont-setting,SmoothingType,%u,Win32 constant\nfont-setting,SmoothingContrast,%u,1000-2200\n",smoothing,smoothing_type,contrast);
    HWND tray = FindWindowW(L"Shell_TrayWnd",NULL); RECT rect;
    if (!tray || !GetWindowRect(tray,&rect)) fail(L"Cannot measure actual Explorer taskbar");
    record("shell,TaskbarHeight,%ld,pixels\nshell,TaskbarWidth,%ld,pixels\nshell,TaskbarLeft,%ld,pixels\nshell,TaskbarTop,%ld,pixels\nshell,TaskbarRight,%ld,pixels\nshell,TaskbarBottom,%ld,pixels\n",rect.bottom-rect.top,rect.right-rect.left,rect.left,rect.top,rect.right,rect.bottom);
    if(!FlushFileBuffers(metadata)||!CloseHandle(metadata))fail(L"Could not flush native metrics");
    ui_font = CreateFontIndirectW(&ncm.lfMessageFont);
    if (!ui_font) fail(L"Could not create native message font");
}
static HWND control(HWND parent,const wchar_t *cls,const wchar_t *text,DWORD style,int x,int y,int w,int h) {
    HWND child=CreateWindowExW(0,cls,text,WS_CHILD|WS_VISIBLE|style,x,y,w,h,parent,NULL,GetModuleHandleW(NULL),NULL);
    if(!child)fail(L"Could not create native Win32 control");
    SendMessageW(child,WM_SETFONT,(WPARAM)ui_font,TRUE);
    return child;
}
static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM wp,LPARAM lp) {
    if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
    return DefWindowProcW(window,message,wp,lp);
}
static BOOL CALLBACK close_fixture(HWND window,LPARAM unused) {
    (void)unused;wchar_t title[256],cls[80];
    GetWindowTextW(window,title,256);GetClassNameW(window,cls,80);
    if((lstrcmpW(cls,L"CabinetWClass")==0 && lstrcmpW(title,L"Classic-demo")==0)||lstrcmpW(cls,L"ConsoleWindowClass")==0||lstrcmpW(cls,L"IEFrame")==0||lstrcmpW(title,L"AutoPlay")==0)PostMessageW(window,WM_CLOSE,0,0);
    return TRUE;
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,LPWSTR command,int show) {
    (void)previous;(void)command;(void)show;
    SetProcessDPIAware();
    int argc; LPWSTR *argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    if(argc!=2 || lstrlenW(argv[1])>=MAX_PATH)fail(L"Usage: native-bench.exe NEW_OUTPUT_DIRECTORY");
    if(lstrcmpW(argv[1],L"--notify")==0) {
        HWND notify=CreateWindowExW(0,L"STATIC",L"Reference notification",0,0,0,0,0,HWND_MESSAGE,NULL,instance,NULL);
        if(!notify)fail(L"Cannot create notification owner");
        NOTIFYICONDATAW data={0};data.cbSize=sizeof(data);data.hWnd=notify;data.uID=1;
        data.uFlags=NIF_ICON|NIF_INFO|NIF_TIP;data.hIcon=LoadIconW(NULL,IDI_INFORMATION);data.dwInfoFlags=NIIF_INFO;
        lstrcpyW(data.szTip,L"Classic reference");lstrcpyW(data.szInfoTitle,L"Classic notification");
        lstrcpyW(data.szInfo,L"Reference notification rendered by Windows 7.");
        if(!Shell_NotifyIconW(NIM_ADD,&data))fail(L"Native notification request failed");
        Sleep(15000);Shell_NotifyIconW(NIM_DELETE,&data);DestroyWindow(notify);LocalFree(argv);return 0;
    }
    if(lstrcmpW(argv[1],L"--scene")==0) {
        // The committed references were captured with ClearType at contrast 1000; other values shift every glyph.
        if(!SystemParametersInfoW(SPI_SETFONTSMOOTHING,TRUE,NULL,SPIF_UPDATEINIFILE|SPIF_SENDCHANGE)||
           !SystemParametersInfoW(SPI_SETFONTSMOOTHINGTYPE,0,(PVOID)(UINT_PTR)FE_FONTSMOOTHINGCLEARTYPE,SPIF_UPDATEINIFILE|SPIF_SENDCHANGE)||
           !SystemParametersInfoW(SPI_SETFONTSMOOTHINGCONTRAST,0,(PVOID)(UINT_PTR)1000,SPIF_UPDATEINIFILE|SPIF_SENDCHANGE))fail(L"Cannot set reference ClearType");
        EnumWindows(close_fixture,0);Sleep(1000);
        wchar_t folder[MAX_PATH];
        if(!GetEnvironmentVariableW(L"USERPROFILE",folder,MAX_PATH-20))fail(L"Cannot locate lab profile");
        lstrcatW(folder,L"\\Classic-demo");
        if((INT_PTR)ShellExecuteW(NULL,L"open",folder,NULL,NULL,SW_SHOWNORMAL)<=32)fail(L"Cannot open fixture folder");
        LocalFree(argv);return 0;
    }
    if(lstrcmpW(argv[1],L"--place")==0) {
        HWND explorer=FindWindowW(L"CabinetWClass",L"Classic-demo");
        if(!explorer)fail(L"Fixture Explorer window not found");
        ShowWindow(explorer,SW_RESTORE);
        if(!SetWindowPos(explorer,NULL,256,120,768,560,SWP_NOZORDER))fail(L"Cannot position fixture window");
        LocalFree(argv);return 0;
    }
    if(lstrcmpW(argv[1],L"--prepare")==0) {
        DEVMODEW mode={0};mode.dmSize=sizeof(mode);
        if(!EnumDisplaySettingsW(NULL,ENUM_CURRENT_SETTINGS,&mode))fail(L"Cannot read current video mode");
        mode.dmPelsWidth=1280;mode.dmPelsHeight=800;mode.dmBitsPerPel=32;
        mode.dmFields=DM_PELSWIDTH|DM_PELSHEIGHT|DM_BITSPERPEL;
        if(ChangeDisplaySettingsW(&mode,CDS_UPDATEREGISTRY)!=DISP_CHANGE_SUCCESSFUL)fail(L"Display driver did not accept 1280x800 at 32 bits");
        LocalFree(argv);return 0;
    }
    lstrcpyW(output,argv[1]); LocalFree(argv);
    if(!CreateDirectoryW(output,NULL))fail(L"Output directory must not already exist");
    export_metadata();
    INITCOMMONCONTROLSEX common={sizeof(common),ICC_WIN95_CLASSES};
    if(!InitCommonControlsEx(&common))fail(L"Cannot initialize common controls");
    WNDCLASSW cls={0};cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.lpszClassName=L"NativeClassicReference";
    cls.hCursor=LoadCursorW(NULL,IDC_ARROW);cls.hbrBackground=GetSysColorBrush(COLOR_BTNFACE);
    if(!RegisterClassW(&cls))fail(L"Cannot register benchmark window");
    HWND window=CreateWindowExW(0,cls.lpszClassName,L"Windows 7 Classic - native control calibration",WS_OVERLAPPEDWINDOW,140,100,1000,560,NULL,NULL,instance,NULL);
    if(!window)fail(L"Cannot create benchmark window");
    wchar_t metrics_file[MAX_PATH];path(metrics_file,L"native-metrics.csv");
    metadata=CreateFileW(metrics_file,FILE_APPEND_DATA,0,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(metadata==INVALID_HANDLE_VALUE)fail(L"Cannot append benchmark geometry");
    RECT client;POINT origin={0,0};
    if(!GetClientRect(window,&client)||!ClientToScreen(window,&origin))fail(L"Cannot measure benchmark geometry");
    record("bench,ClientX,%ld,pixels\nbench,ClientY,%ld,pixels\nbench,ClientWidth,%ld,pixels\nbench,ClientHeight,%ld,pixels\n",origin.x,origin.y,client.right,client.bottom);
    if(!FlushFileBuffers(metadata)||!CloseHandle(metadata))fail(L"Cannot save benchmark geometry");
    control(window,L"STATIC",L"Genuine Windows 7 controls; system message font; 96 DPI",0,24,20,800,24);
    control(window,L"BUTTON",L"Normal",BS_PUSHBUTTON,24,65,130,26);
    HWND pressed=control(window,L"BUTTON",L"Pressed",BS_PUSHBUTTON,174,65,130,26);
    SendMessageW(pressed,BM_SETSTATE,TRUE,0);
    HWND disabled=control(window,L"BUTTON",L"Disabled",BS_PUSHBUTTON,324,65,130,26);EnableWindow(disabled,FALSE);
    HWND focus=control(window,L"BUTTON",L"Focused",BS_PUSHBUTTON,474,65,130,26);
    control(window,L"BUTTON",L"Default",BS_DEFPUSHBUTTON,624,65,130,26);
    control(window,L"BUTTON",L"Unchecked",BS_AUTOCHECKBOX,24,120,150,24);
    HWND checked=control(window,L"BUTTON",L"Checked",BS_AUTOCHECKBOX,190,120,150,24);SendMessageW(checked,BM_SETCHECK,BST_CHECKED,0);
    HWND off=control(window,L"BUTTON",L"Disabled checked",BS_AUTOCHECKBOX,356,120,190,24);SendMessageW(off,BM_SETCHECK,BST_CHECKED,0);EnableWindow(off,FALSE);
    control(window,L"BUTTON",L"Radio",BS_AUTORADIOBUTTON,24,162,150,24);
    HWND radio=control(window,L"BUTTON",L"Selected radio",BS_AUTORADIOBUTTON,190,162,180,24);SendMessageW(radio,BM_SETCHECK,BST_CHECKED,0);
    control(window,L"EDIT",L"Editable text",WS_BORDER|ES_AUTOHSCROLL,24,215,280,24);
    HWND edit=control(window,L"EDIT",L"Disabled text",WS_BORDER|ES_AUTOHSCROLL,324,215,280,24);EnableWindow(edit,FALSE);
    HWND combo=control(window,L"COMBOBOX",L"",CBS_DROPDOWNLIST|WS_VSCROLL,24,265,280,200);
    SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)L"Selected option");SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)L"Another option");SendMessageW(combo,CB_SETCURSEL,0,0);
    control(window,L"SCROLLBAR",L"",SBS_HORZ,324,265,280,GetSystemMetrics(SM_CYHSCROLL));
    control(window,L"BUTTON",L"Group box",BS_GROUPBOX,24,330,580,120);
    control(window,L"STATIC",L"The reference is rendered by Windows, not a web simulator.",0,44,368,540,24);
    ShowWindow(window,SW_SHOW);UpdateWindow(window);
    SendMessageW(window,WM_CHANGEUISTATE,MAKEWPARAM(UIS_CLEAR,UISF_HIDEFOCUS),0);SetFocus(focus);
    MSG msg;int result;
    while((result=GetMessageW(&msg,NULL,0,0))>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
    if(result<0)fail(L"Window message loop failed");
    DeleteObject(ui_font);return 0;
}
void WINAPI reference_entry(void) {
    ExitProcess(wWinMain(GetModuleHandleW(NULL),NULL,NULL,SW_SHOW));
}
