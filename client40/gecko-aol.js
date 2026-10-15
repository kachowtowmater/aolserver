// Wine Gecko settings for AOL 4.0's World Wide Web window (copied into
// <prefix>/drive_c/windows/syswow64/gecko/<ver>/wine_gecko/defaults/pref/ by aol40_client.py web).
// AOL's x86 client runs under emulation on ARM machines (FEX/Rosetta) where code generated at run
// time is the usual cause of crashes: the JavaScript JITs crashed the browser inside xul.dll.
// Pages come through WRP as pictures, so nothing visible is lost.
pref("javascript.options.baselinejit", false);
pref("javascript.options.ion", false);
pref("javascript.options.asmjs", false);
pref("javascript.options.wasm", false);
pref("javascript.options.native_regexp", false);
pref("layers.acceleration.disabled", true);
pref("gfx.direct2d.disabled", true);
