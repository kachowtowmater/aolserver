#!/bin/bash
# Rebuild server/art from the IDX files kept under disc/harvest/ in priority order.
# Tier 1 (US 3.0, the client's own family): first-found wins unless a later copy is larger.
# Tiers 2-4 (US 4.0, 2.5, international): --fill-only (only GIDs still missing).
set -u
A=~/aol-revival
H=$A/disc/harvest
T="python3 -I $A/tools/harvest_art.py"
rm -f $A/server/art/*.bin $A/server/art/SOURCES.tsv

declare -A SEEN
run() { # item fill? paths...
  local item=$1 fill=$2; shift 2
  SEEN[$item]=1
  local paths=()
  for p in "$@"; do [ -e "$p" ] && paths+=("$p"); done
  [ ${#paths[@]} -eq 0 ] && return
  if [ "$fill" = fill ]; then $T --item "$item" --fill-only "${paths[@]}" 2>/dev/null
  else $T --item "$item" "${paths[@]}" 2>/dev/null; fi
}

# tier 1: US Windows 3.0 (the target client build first)
run Proven_Faster_Internet_Experience_AOL_Version_3.0_PA1097R23 - "$H/PA1097R23"
for i in AmericaOnlineVersion30ForWindows1996 aol30_1996-08 america-online-version-30-for-windows-1996.disk-1of-1 \
         aol-v-3.0 aol-setup-32 aol-16-bit-setup aol_ver_30_202506 aol-ver.-3.0 setup_20230329 \
         America_Online_R03066_1996 America_Online_The_Worlds_Most_Popular_Internet_Online_Service_Version_3.0_is_He \
         AOL_Version_3_Sign_On_Now_00001354_America_On-Line america-online-the-future.-now-available-version-3.0-is-here-r-02352-1996 \
         America_Online_Explore_for_50_Hours_Free_New_Version_RO2331 america-online-explore-for-15-hours-free-new-version-ro-2245 \
         adv_new_america_online AOL_VER_30 aol-ver-30 America_OnLine_1997 America_Online_3.0_With_50_Free_Hours_A497R78 \
         America_Online_-_Sign_On_Today_-_50_Free_Hours_AOL_AM1297R9 America_Online_NEW_Version_3.0_A298R1_50_Hours_Free \
         America_Online_NEW_Version_3.0_A698R4_100_Hours_Free America_Online_Great_Features_for_the_Family_AM898R15_Its_a_Family_Thing \
         AOL_Online_-_Version_3.0_Is_Here_AM1198R6_AOL_1998 Nova_Software_AOLAmericaOnline_USA_v3.0 the-aol-collection \
         aol-v-3.0i-ps-2.97; do
  run "$i" - "$H/$i/idx"
done
run aol-floppies - $H/aol-floppies/idx/*-30*
# tier 2: US 4.0 (the 3.0 installers on these CDs + the 4.0 client DBs), fill only
run aol40-cd fill "$H/aol40-cd" "$A/disc/aol40/iso/WIN9X/ART/ART5.IDX"
for i in Welcome_to_America_Online_Inc_AR022_America_On-Line AR518 \
         A_Whole_Month_to_Enjoy_100_Free_Hours_All_New_Version_4.0_A599R1_America_Online All_New_and_Improved_AOL_Version_4.0_1999 \
         America_Online_100_Hours_Free_The_All-New_Version_4.0_S1198RPY America_Online_Version_4.0_250_Hours_Free_America_Online_A0899R101-B_1999 \
         AOL_Platinum_Premier_Version_4.0_250_Free_Hours_CR899R1-B_AOL_1999 America_Online_AR516_1999 America_Online_AR526_1999 \
         aol-4.0 aol-v-4 setup-323 aol-4.0i; do
  run "$i" fill "$H/$i/idx"
done
# tier 3: US 2.5, fill only
run aol-floppies fill $H/aol-floppies/idx/*-25*
for i in America_Online_V2.5i_114.20 aol-v-2.5i-114.20-1996-08-27 aol-v-2.5i-114.20-1996-07-22 aol-v-2.5i-114.19 \
         aol-v-2.5i-114.18_202011 10_Free_Hours_Online_With_AOL_for_Windows_V25-11420 aol25_199506 aol25 aol250g \
         aol-for-windows-2-5-1-5 aol_setup_disk 1996_01_10_TracerST America_Online_00001115; do
  run "$i" fill "$H/$i/idx"
done
# tier 4: everything else (CA/UK/SE/DE/FR/BR/JA builds), fill only
for d in "$H"/*/; do
  i=$(basename "$d")
  [ -n "${SEEN[$i]:-}" ] && continue
  run "$i" fill "$d/idx"
done
SEEN[aol-floppies]=; run aol-floppies fill "$H/aol-floppies/idx"
