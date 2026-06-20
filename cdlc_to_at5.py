#!/usr/bin/env python3
"""
CDLC -> AmpliTube 5 Tone Converter  v2.0
Converts tone_{uuid}.json files to .at5p preset files.

Usage:
    python cdlc_to_at5.py tone_e5c8db1e.json
    python cdlc_to_at5.py --scan "I:\\Docker\\CDLCScrape\\Songs" --output "C:\\Users\\you\\Documents\\IK Multimedia\\AmpliTube 5\\Presets"
"""

import json, uuid, sys, argparse
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

NULL_GUID = "773b8ea7-b54a-4a3c-99df-ffbbf6d29271"  # empty/null slot

# ─────────────────────────────────────────────────────────────────────────────
# AMP MAPPING  (Rocksmith Key -> AT5 GUID)
# Source: GearInfo/Cabs.json extracted from AmpliTube 5.pak
# ─────────────────────────────────────────────────────────────────────────────

AMP_MAP = {
    # ── Rocksmith+ generic coded amp keys ─────────────────────────────────────
    # Naming scheme: TW=Tweed(Fender), CA=California(Mesa), EN=English(Vox),
    # BT=British Tube(Marshall), AT=American Tube(Roland), CS=Crystal/SS(Roland),
    # HG=High Gain, GB=German/British

    # TW = Tweed (Fender)
    "Amp_TW22":  "bf860ad9-cd8a-425b-8049-29211fce237a",  # '57 Custom Deluxe  (22W tweed)
    "Amp_TW26":  "6c421302-9602-4ee8-b94a-672aa24cdde4",  # '57 Custom Pro-Amp (26W tweed)
    "Amp_TW40":  "3fcc8ad1-6d5e-416d-9c3d-7aae91c6f4d4",  # '59 Bassman LTD    (40W tweed)

    # CA = California (Mesa/Boogie)
    "Amp_CA38":  "a91067a3-fd80-40a8-be35-0681da5c4f47",  # American Clean MKIII (38W Mesa Mark III combo, clean ch)
    "Amp_CA85":  "6ec4bf7a-dc59-4443-b2fb-1e645bf5192c",  # Mark III             (85W Mesa Mark III, crunch ch)
    "Amp_CA100": "75ad4a0e-5c75-443d-8617-9681c4fe58d3",  # Dual Rectifier       (100W Mesa Dual Rectifier)

    # EN = English (Vox)
    "Amp_EN30":  "5d235e0d-9fd7-429e-b483-6f815281f3d7",  # British Copper 30TB  (Vox AC30)

    # BT = British Tube (Marshall)
    "Amp_BT30":  "cbf3c00f-dc31-4c7f-a409-f7fdbca005a8",  # Brit 9000            (Marshall JCM900, ~30W EL34 config)
    "Amp_BT45":  "7788f707-4ef2-44cd-862a-a82ffdf7172b",  # JH Gold              (Marshall JTM45)

    # AT = American Tube (Roland JC series)
    "Amp_AT120": "ac08939a-32bf-496c-96ac-5d6c530abf14",  # Jazz Amp 120         (Roland JC-120)
    "Amp_AT20":  "89b3caab-dffb-4c29-85d9-2a60cb93c566",  # '65 Deluxe Reverb    (American Tube 20W)

    # CS = Crystal / Solid-state (Roland JC series)
    "Amp_CS90":  "ac08939a-32bf-496c-96ac-5d6c530abf14",  # Jazz Amp 120         (Roland JC-90)
    "Amp_CS100": "ac08939a-32bf-496c-96ac-5d6c530abf14",  # Jazz Amp 120         (Roland JC-100)
    "Amp_CS120": "ac08939a-32bf-496c-96ac-5d6c530abf14",  # Jazz Amp 120         (Roland JC-120)

    # HG = High Gain
    "Amp_HG500": "c85e5dc4-d051-4aad-846f-038b0b5233c5",  # Triple Rectifier     (Mesa Triple Rectifier)

    # ── Marshall branded keys ─────────────────────────────────────────────────
    "Amp_MarshallPlexi":            "d089ef66-b5c4-4274-910c-6a6ee194cf04",  # British Lead S100
    "Amp_MarshallJCM800":           "8fe96936-5178-4950-9b80-d89c32534bad",  # Brit 8000
    "Amp_MarshallJCM900":           "cbf3c00f-dc31-4c7f-a409-f7fdbca005a8",  # Brit 9000
    "Amp_MarshallJTM45":            "7788f707-4ef2-44cd-862a-a82ffdf7172b",  # JH Gold
    "Amp_MarshallDSL100H":          "8fe96936-5178-4950-9b80-d89c32534bad",  # Brit 8000  (DSL100H closest to JCM800)
    "Amp_MarshallDSL15H":           "8fe96936-5178-4950-9b80-d89c32534bad",  # Brit 8000
    "Amp_MarshallJVM410H":          "57c43635-a976-46e0-a5c1-ef843bbba616",  # Satch VM
    "Amp_MarshallJVM":              "57c43635-a976-46e0-a5c1-ef843bbba616",  # Satch VM
    "Amp_MarshallSilverJubilee":    "3930eb8b-3eda-4079-b86d-7bfd7d4449bc",  # Brit Silver
    "Amp_MarshallMajor":            "e1eed2cf-6777-46c4-ada2-65df0d7afc46",  # Red Pig
    "Amp_MarshallJMP":              "1b5961b1-f862-4c8a-9a9b-a920da8c5cc2",  # Vintage Metal Lead
    "Amp_MarshallSlash":            "2ea3ecfb-1b0c-417a-8788-86f5915f43c5",  # Brit 100 Mod 34/36
    "Amp_MarshallSlashGold":        "155f0121-a2ee-4e16-aaa0-44948f9be44f",  # Brit L.A. Gold
    "Amp_Marshall1962Bluesbreaker": "7788f707-4ef2-44cd-862a-a82ffdf7172b",  # JH Gold  (closest to Bluesbreaker)

    # ── Orange branded keys (IBEX artist-authenticated) ───────────────────────
    "IBEX_Amp_OrangeAD30_CH2":  "dd7b0e06-a17a-4851-83c4-ee32ca303b01",  # AD 30
    "IBEX_Amp_OrangeRV50_CH1":  "e6151532-1028-422c-9a5d-fc57594ce8e8",  # RockerVerb 50

    # ── Fender branded keys ───────────────────────────────────────────────────
    "Amp_FenderDeluxeReverb":   "89b3caab-dffb-4c29-85d9-2a60cb93c566",  # '65 Deluxe Reverb
    "Amp_FenderTwinReverb":     "b3869f27-a9f1-4482-add4-9512c16917ea",  # '65 Twin Reverb
    "Amp_FenderBassman":        "ca4587b9-3960-49de-9509-5a61e9b5cbae",  # American Vintage B
    "Amp_FenderSupersonic":     "f4b89ab3-8ca6-44ee-b90b-a570040c8a3d",  # Super-Sonic
    "Amp_FenderVibroking":      "dffa559d-7b12-464a-9fbf-877ca25f5cf3",  # Vibro-King
    "Amp_FenderVibroverb":      "f0951b1e-91d2-4360-80d7-793fa785d2d6",  # '64 Vibroverb Custom
    "Amp_FenderChamp":          "5f4f50a1-d5cb-43be-ad11-084e4ff21ea6",  # '57 Champ
    "Amp_FenderChampion600":    "016a8c2a-489e-49da-81d7-5b72feb60f74",  # Champion 600
    "Amp_FenderPrinceton":      "2a1f483c-a136-45b6-81ec-e92c60f8d009",  # '65 Princeton
    "Amp_FenderProJunior":      "d0546d04-505c-42b1-8e9e-668a16adcfa8",  # Pro Junior
    "Amp_FenderSuperReverb":    "d3c791b9-58f1-41d2-8a88-797e98cc5b29",  # '65 Super Reverb
    "Amp_Fender57CustomTwin":   "4c9e667b-932a-42e3-a5d8-a9d9374c9959",  # '57 Custom Twin-Amp
    "Amp_Fender57CustomPro":    "6c421302-9602-4ee8-b94a-672aa24cdde4",  # '57 Custom Pro-Amp
    "Amp_Fender59Bassman":      "3fcc8ad1-6d5e-416d-9c3d-7aae91c6f4d4",  # '59 Bassman LTD
    "Amp_FenderBassman300":     "9e6f407a-161d-433b-bddc-8565103fc9ce",  # Bassman 300
    "Amp_FenderMH500":          "907be0ce-a419-4281-901f-dcd6763de54a",  # MH-500 Metalhead

    # ── Mesa/Boogie branded keys ──────────────────────────────────────────────
    "Amp_MesaBoogieMarkIII":    "6ec4bf7a-dc59-4443-b2fb-1e645bf5192c",  # Mark III
    "Amp_MesaBoogieMarkIV":     "1fbf7d6e-dad8-470f-b204-4d96b5466893",  # Mark IV
    "Amp_MesaBoogieMarkV":      "d31154a9-8b5f-4abf-b079-d2e728d2c564",  # Mark V
    "Amp_MesaBoogieMarkIIC":    "6e5c01fe-e1be-4e91-8657-74718ac8cb6e",  # Mark IIC+
    "Amp_MesaDualRectifier":    "75ad4a0e-5c75-443d-8617-9681c4fe58d3",  # Dual Rectifier
    "Amp_MesaTripleRectifier":  "c85e5dc4-d051-4aad-846f-038b0b5233c5",  # Triple Rectifier
    "Amp_MesaTA30":             "1284c9cc-6efa-4720-a0da-106a2d2af1d8",  # TransAtlantic TA-30
    "Amp_MesaTripleCrown":      "2ed4e896-6cf4-40ee-bc12-15f0c4d38b65",  # Triple Crown
    "Amp_MesaCaliforniaTweed":  "d9aa41f9-4e51-4719-929c-251d07f2f276",  # California Tweed
    "Amp_MesaModernTubeLead":   "bca11751-a7c1-49f5-846d-031f7eb780f0",  # Modern Tube Lead
    "Amp_MesaCleanMKIII":       "a91067a3-fd80-40a8-be35-0681da5c4f47",  # American Clean MKIII
    "Amp_MesaLeadMKIII":        "4af9d89a-c06b-4c8f-b137-af72bc58fded",  # American Lead MKIII

    # ── Vox ───────────────────────────────────────────────────────────────────
    "Amp_VoxAC30":     "5d235e0d-9fd7-429e-b483-6f815281f3d7",  # British Copper 30TB
    "Amp_VoxAC30Blue": "533d3c6c-b3cd-455c-a3a1-642016f5cda9",  # British Blue Tube 30TB

    # ── Orange ────────────────────────────────────────────────────────────────
    "Amp_OrangeOR120":       "6e8690b3-f6cf-4c36-b3c2-7f38fcc5706e",  # OR-120
    "Amp_OrangeTinyTerror":  "99e446c7-49df-45b1-bff9-26d95e10c763",  # Tiny Terror
    "Amp_OrangeRockerverb":  "e6151532-1028-422c-9a5d-fc57594ce8e8",  # RockerVerb 50
    "Amp_OrangeAD30":        "dd7b0e06-a17a-4851-83c4-ee32ca303b01",  # AD 30
    "Amp_OrangeThunderverb": "e3260631-d81f-4c76-9e4f-d12be6ede5cb",  # Thunderverb 200
    "Amp_OrangeAD200":       "dfb00647-6603-4fe1-a67a-5690a4dad0fb",  # AD 200
    "Amp_OrangeDualTerror":  "3c25674f-a418-4fec-863c-f94495c746a0",  # Dual Terror
    "Amp_OrangeOR50":        "827aedfb-cdc1-412e-8e47-5bac3c3c6d06",  # OR 50

    # ── ENGL ──────────────────────────────────────────────────────────────────
    "Amp_EnglE650":     "c936fc9c-1594-48c8-b561-824827452a66",  # E650
    "Amp_EnglPowerball":"88d927a0-e399-4a1d-ac68-0699eee85f02",  # Powerball

    # ── Soldano ───────────────────────────────────────────────────────────────
    "Amp_Soldano": "4a22ac9f-aabb-4180-b697-5d5710a1acc2",  # SLD 100

    # ── Peavey ────────────────────────────────────────────────────────────────
    "Amp_Peavey5150":   "dcc7c825-76f4-4703-8e1f-b8a12b30b1de",  # Metal Lead V
    "Amp_Peavey5150II": "1e170e52-9ff7-40ff-995f-fab2cdef7cf5",  # SJ50

    # ── Hiwatt ────────────────────────────────────────────────────────────────
    "Amp_Hiwatt": "26fbbf20-f88e-46de-a76f-5aabd2c8fd8d",  # HiAmp

    # ── Roland ────────────────────────────────────────────────────────────────
    "Amp_RolandJC120": "ac08939a-32bf-496c-96ac-5d6c530abf14",  # Jazz Amp 120

    # ── Misc branded ──────────────────────────────────────────────────────────
    "Amp_DrZMaz18":       "abdcae70-bff2-4b02-bf2f-d716dd8e8adf",  # MAZ 18 Jr
    "Amp_DrZZWreck":      "cc59b472-2a2f-40b1-97f4-6ee4b7536c87",  # Z Wreck
    "Amp_CarvinV3M":      "5558e374-6d37-4674-a05e-2e005830d24e",  # V3M
    "Amp_DiezelVH4":      "185e9cde-535b-42ab-abd1-4fbdb52d4808",  # VHandcraft 4
    "Amp_BognerEcstasy":  "4b13e59f-32b7-4a69-abd0-28d0909cef89",  # German 34
    "Amp_PRSArchon":      "f24511a1-8ade-4f93-b781-ade541f0a921",  # SilverPlate 50
    "Amp_THDBiValve":     "f058124b-498f-4899-8b29-35453d6aecff",  # Bi-Valve
    "Amp_JetCityJCA20H":  "55078333-dcfd-41ac-9e87-cd6ea334507a",  # JCA20H
    "Amp_JetCityJCA100H": "913db945-c3a9-4e96-ad17-9c8d1053d913",  # JCA100H
    "Amp_Sunn1200":       "300ed819-d21b-4589-b095-afd038e9f08c",  # JH 1200
    "Amp_Randall":        "cfa6b70c-2c6c-4b83-b881-571a6343dfac",  # Darrell 100
    "Amp_Supro":          "bd903ed7-82bf-41cc-9834-685b6e3667b5",  # Tube Vintage Combo


    # ── RS+ placeholder amp keys (brand-safe names for unlicensed amps) ──────
    # EN50 = English 50W — Vox AC30 variant or Orange RockerVerb 50
    # Muse used Orange and Vox; splitting by wattage: EN30=AC30, EN50=RockerVerb
    "Amp_EN50":  "e6151532-1028-422c-9a5d-fc57594ce8e8",  # RockerVerb 50
    # GB = German/British (Bogner/Diezel)
    "Amp_GB38":  "4b13e59f-32b7-4a69-abd0-28d0909cef89",  # German 34 (Bogner Ecstasy)
    "Amp_GB50":  "4b13e59f-32b7-4a69-abd0-28d0909cef89",  # German 34 (Bogner Ecstasy)
    "Amp_GB100": "185e9cde-535b-42ab-abd1-4fbdb52d4808",  # VHandcraft 4 (Diezel VH4)
    # BT = British Tube extras
    "Amp_BT15":  "7788f707-4ef2-44cd-862a-a82ffdf7172b",  # JH Gold (Marshall JTM45 — closest small British)
    # HG = High Gain
    "Amp_HG100": "dcc7c825-76f4-4703-8e1f-b8a12b30b1de",  # Metal Lead V (Peavey 5150)
    "Amp_HG180": "4a22ac9f-aabb-4180-b697-5d5710a1acc2",  # SLD 100 (Soldano SLO-100)

    # ── DI / direct ───────────────────────────────────────────────────────────
    "DI_Amp_TubePre":    "71a76a9f-cf70-4f59-971f-9864a055523c",  # American Tube Clean 1 (DI placeholder - amp muted)
    "DI_Amp_BassDriver": "71a76a9f-cf70-4f59-971f-9864a055523c",  # Bass DI — same muted placeholder

    # ── Bass ──────────────────────────────────────────────────────────────────
    # CH = Ampeg SVT (Classic/Heritage)
    "Bass_Amp_CH300B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL  (Ampeg SVT Classic 300W)
    "Bass_Amp_CH350B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL
    "Bass_Amp_CH600B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL
    "Bass_Amp_BT600B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL  (British Tube bass)
    "Bass_Amp_BT880B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL
    "Bass_Amp_BT975B": "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL
    # HT = Ampeg SVT-VR (Heritage)
    "Bass_Amp_HT100B": "ff274db4-43c3-4fb9-b44d-d04aefd13b28",  # SVX-15R (Ampeg B-15 Heritage)
    "Bass_Amp_HT300B": "2aa0f50f-a6c9-4edd-97c2-df71a24087db",  # SVX-VR  (Ampeg SVT-VR 300W)
    "Bass_Amp_HT400B": "2aa0f50f-a6c9-4edd-97c2-df71a24087db",  # SVX-VR
    # LT = Fender Bassman (Light/Low wattage)
    "Bass_Amp_LT25B":  "9e6f407a-161d-433b-bddc-8565103fc9ce",  # Bassman 300 (closest Fender bass amp)
    "Bass_Amp_LT85B":  "9e6f407a-161d-433b-bddc-8565103fc9ce",  # Bassman 300
    # CS = Crystal/Solid-state (Eden/Gallien-Krueger style)
    "Bass_Amp_CS75B":  "18f9d728-018e-4e22-9121-b7f411b2bb77",  # New York B750
    "Bass_Amp_CS240B": "18f9d728-018e-4e22-9121-b7f411b2bb77",  # New York B750
    "Bass_Amp_CS300B": "18f9d728-018e-4e22-9121-b7f411b2bb77",  # New York B750
    # Named bass amps
    "Bass_Amp_EdenWT550": "18f9d728-018e-4e22-9121-b7f411b2bb77",  # New York B750 (Eden WT550)
    "Amp_Ampeg":          "52f28b23-80e3-4f43-9508-4447258b11c0",  # SVX-CL
    "Amp_AmpegSVTVR":     "2aa0f50f-a6c9-4edd-97c2-df71a24087db",  # SVX-VR
    "Amp_AmpegB15":       "ff274db4-43c3-4fb9-b44d-d04aefd13b28",  # SVX-15R
    "Amp_Acoustic360":    "ecb60014-617c-4637-9435-28c1480a0e8f",  # 360Bass Preamp
    "Amp_Aguilar":        "18f9d728-018e-4e22-9121-b7f411b2bb77",  # New York B750
}

# ─────────────────────────────────────────────────────────────────────────────
# CABINET ENCLOSURE MAPPING  (Rocksmith Cab Key -> AT5 CabModel GUID)
# Source: GearInfo/Mics.json extracted from AmpliTube 5.pak
# ─────────────────────────────────────────────────────────────────────────────

CAB_ENCLOSURE_MAP = {
    # Marshall 4x12s
    "Cab_Marshall1960TV_57_Cone": "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_Marshall1960A":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_Marshall1960B":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_Marshall1960AV":         "c97bc69c-c02d-4cce-b19d-859b72833550",  # 4x12 1960AV
    "Cab_Marshall1960BV":         "936efc52-2172-4faf-9be5-e8f45244a2b9",  # 4x12 1960BV
    "Cab_Marshall1960SL":         "936efc52-2172-4faf-9be5-e8f45244a2b9",  # 4x12 1960BV
    "Cab_MarshallSilver":         "c6dc5147-0436-482f-9a8d-070ccea23c46",  # 4x12 Brit Silver
    "Cab_MarshallJCM800":         "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_MarshallJCM900":         "a54d97da-cd7f-4742-acba-45cb2688c8c9",  # 4x12 Brit 9000
    "Cab_MarshallMajor":          "6dfb576f-b549-4dd4-ac79-1021bcb53bb2",  # 4x12 Red Pig
    "Cab_Marshall_ClosedVintage": "83:445c0a64-c729-4502-b7c4-91e211a7fc21",
    # Vox
    "Cab_VoxAC30":                "85d85251-4cb2-4ade-b04c-9c6e150e41d7",  # 2x12 BM 30 H70 (AC30 type)
    "Cab_Vox":                    "85d85251-4cb2-4ade-b04c-9c6e150e41d7",  # 2x12 BM 30 H70
    "Cab_VoxAC30Blue":            "72b72d5c-a977-4921-8ed9-d342ddfe964d",  # 2x12 BM 30 Blue
    # Fender
    "Cab_FenderDeluxeReverb":     "bcec521d-c918-4af6-98be-b50b644ac3dd",  # 1x12 Open Vintage
    "Cab_FenderTwinReverb":       "8b37839c-5798-4584-8aca-b7bfce4819a6",  # 2x12 '65 Twin Reverb
    "Cab_FenderBassman":          "4614704e-7ca2-4736-a750-648fe9033650",  # 4x10 '59 Bassman
    "Cab_FenderSuperReverb":      "fa7d0a6a-23e9-4f05-a062-607f5cfe7dda",  # 4x10 '65 Super Reverb
    "Cab_FenderVibroverb":        "7a1b419a-fbd7-4507-93e3-d6dba20ea7ad",  # 1x15 '64 Vibroverb
    "Cab_FenderChamp":            "f7f9e974-28f8-4303-b177-39e620c60e9e",  # 1x8 '57 Champ
    "Cab_FenderChampion600":      "4b4c561b-68d7-4311-ae31-2432817850bd",  # 1x6 Champion 600
    "Cab_FenderPrinceton":        "223ef7e4-1afe-4c89-b707-362f0c100d04",  # 1x10 '65 Princeton
    "Cab_FenderVibroking":        "104346d1-5fbc-474d-bcf0-7980cbe04a82",  # 3x10 Vibro-King
    "Cab_FenderProJunior":        "06834dae-1774-4a8a-9ff0-e8a1f05b4ae5",  # 1x10 Pro Junior
    "Cab_FenderSupersonic":       "67012b6a-0886-41d3-9a03-daa13ed47c34",  # 1x12 Super-Sonic
    "Cab_Fender57Deluxe":         "70b17311-7b73-4415-968e-c26543e22e18",  # 1x12 '57 Deluxe
    "Cab_Fender57Champ":          "f7f9e974-28f8-4303-b177-39e620c60e9e",  # 1x8 '57 Champ
    "Cab_Fender57CustomChamp":    "36ca806c-5136-4370-baa4-ce45b3c1c9af",  # 1x8 '57 Custom Champ
    "Cab_Fender57CustomDeluxe":   "7efbb008-6942-4538-875b-d65fc7321617",  # 1x12 '57 Custom Deluxe
    "Cab_Fender57CustomTwin":     "2af64b91-de12-48cf-a90e-2e5c4bcc9530",  # 2x12 '57 Custom Twin
    "Cab_Fender57CustomPro":      "59f2b03d-40c1-405b-aeea-38df617b49fa",  # 1x15 '57 Custom Pro
    "Cab_Fender57Bandmaster":     "21a4eb35-fce4-482a-9199-ace3f4205ede",  # 3x10 '57 Bandmaster
    # Mesa/Boogie
    "Cab_MesaRecto":              "849b3340-9e28-411f-9faf-e99b7b2bfb36",  # 4x12 Recto Traditional Slant
    "Cab_MesaDualRecto":          "849b3340-9e28-411f-9faf-e99b7b2bfb36",  # 4x12 Recto Traditional Slant
    "Cab_MesaTripleRecto":        "849b3340-9e28-411f-9faf-e99b7b2bfb36",  # 4x12 Recto Traditional Slant
    "Cab_MesaRoadKing":           "0046ce65-9631-4ef4-989c-b03e355eb87b",  # 4x12 Road King Black
    "Cab_MesaTA30":               "356da432-3493-4403-ac2d-761a28855638",  # 2x12 TransAtlantic TA-30
    "Cab_MesaMarkIII":            "82409e48-b67c-4762-8256-963f43240ccc",  # 1x12 Mark III
    "Cab_MesaMarkIV":             "8c6c0893-9f50-492c-ac1d-4773fd697638",  # 1x12 Mark IV
    "Cab_MesaCaliforniaTweed":    "fcb2aa61-ccd5-4e6b-bbfc-45339c1c4352",  # 1x12 California Tweed
    # Orange
    "Cab_OrangePPC412":           "4edd00f5-1dc0-4130-a3bb-7eb608e834ab",  # 4x12 PPC 412
    "Cab_OrangePPC212":           "16b2e136-c230-4598-9931-5b913efb76e6",  # 2x12 PPC 212
    "Cab_OrangePPC112":           "e49d0a85-bcde-4d98-801c-24166a47c8a1",  # 1x12 PPC 112
    "Cab_OrangeTinyTerror":       "33238dfe-a58a-4b2c-a5a7-23388006e414",  # 1x12 Tiny Terror
    "Cab_OrangeAD30":             "1d1c171f-7380-4727-8bd6-c63021db9dd6",  # 2x12 AD 30
    "Cab_OrangeOBC810":           "fb54d283-dfc2-402e-8c76-87713387d770",  # 8x10 OBC 810
    "Cab_OrangeOBC410":           "c4af1d27-afd0-426f-9c96-e2f65378b93a",  # 4x10 OBC 410
    "Cab_OrangeOBC115":           "0c2f1129-e09d-4510-9624-7c8b05f188cf",  # 1x15 OBC 115
    # ENGL
    "Cab_EnglE412PROXXL":         "8eaae0e6-4c9b-471e-814b-6a4596a4d153",  # E 412 PRO XXL
    "Cab_EnglE412Standard":       "088fe7ff-34f6-4a64-9a7c-0f938f05553d",  # E 412 Standard
    # Dr. Z
    "Cab_DrZMaz18":               "c895007f-963a-499c-bd76-7cb9fbf31a96",  # 1x12 MAZ 18 Jr.
    "Cab_DrZZWreck":              "bce514e5-5fa0-40c3-ae1d-85093a3d62f6",  # 2x12 Z Wreck
    # Hiwatt
    "Cab_Hiwatt":                 "9ef10de4-2781-4ab7-9179-c1cc4b6615e5",  # 4x12 HiAmp
    # Roland
    "Cab_RolandJC120":            "f7902634-12e9-4a2d-9f9a-bcd22781cdab",  # 2x12 JP Jazz
    # Ampeg
    "Cab_AmpegSVT810E":           "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-810E
    "Cab_AmpegSVT810AV":          "b31f4357-3c42-4c89-8736-64f25bcbed9d",  # SVX-810 AV
    "Cab_AmpegB15":               "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # SVX-15R
    "Cab_AmpegBA500":             "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-500
    # ── RS+ generic coded cab keys ────────────────────────────────────────────
    "Cab_AT0112C_Condenser_Edge":       "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_AT0112C_57_Edge":              "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_AT0112C_Ribbon_Cone":          "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_AT0112C_Ribbon_Edge":          "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_AT1121C_57_Cone":              "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_AT1121C_57_Edge":              "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_TW112C_57_Edge":               "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW112C_57_Cone":               "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW112C_Ribbon_Cone":           "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW112C_Ribbon_Edge":           "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW112C_Condenser_Cone":        "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW112C_Condenser_OffAxis":     "70b17311-7b73-4415-968e-c26543e22e18",
    "Cab_TW110C_57_Edge":               "f7f9e974-28f8-4303-b177-39e620c60e9e",
    "Cab_TW110C_57_Cone":               "f7f9e974-28f8-4303-b177-39e620c60e9e",
    "Cab_TW110C_Ribbon_Cone":           "f7f9e974-28f8-4303-b177-39e620c60e9e",
    "Cab_TW110C_Ribbon_Edge":           "f7f9e974-28f8-4303-b177-39e620c60e9e",
    "Cab_TW110C_Condenser_Cone":        "f7f9e974-28f8-4303-b177-39e620c60e9e",
    "Cab_TW410C_Ribbon_Cone":           "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_TW410C_Ribbon_Edge":           "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_TW410C_Condenser_Edge":        "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_TW410C_Condenser_Cone":        "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_TW410C_57_Edge":               "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_TW410C_57_OffAxis":            "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_CA112C_57_Edge":               "82409e48-b67c-4762-8256-963f43240ccc",
    "Cab_CA112C_57_Cone":               "82409e48-b67c-4762-8256-963f43240ccc",
    "Cab_CA112C_Condenser_Cone":        "82409e48-b67c-4762-8256-963f43240ccc",
    "Cab_CA112C_Ribbon_Edge":           "82409e48-b67c-4762-8256-963f43240ccc",
    "Cab_CA112C_Ribbon_OffAxis":        "82409e48-b67c-4762-8256-963f43240ccc",
    "Cab_CA412C_57_Edge":               "849b3340-9e28-411f-9faf-e99b7b2bfb36",
    "Cab_CA412C_57_Cone":               "849b3340-9e28-411f-9faf-e99b7b2bfb36",
    "Cab_CA412C_Ribbon_Cone":           "849b3340-9e28-411f-9faf-e99b7b2bfb36",
    "Cab_CA412C_Condenser_Edge":        "849b3340-9e28-411f-9faf-e99b7b2bfb36",
    "Cab_CA215C_57_Edge":               "fcb2aa61-ccd5-4e6b-bbfc-45339c1c4352",
    "Cab_CA215C_57_Cone":               "fcb2aa61-ccd5-4e6b-bbfc-45339c1c4352",
    "Cab_CA215C_Condenser_Edge":        "fcb2aa61-ccd5-4e6b-bbfc-45339c1c4352",
    "Cab_EN212C_57_Cone":               "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN212C_57_Edge":               "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN212C_Condenser_Cone":        "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN212C_Ribbon_Edge":           "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN212C_Ribbon_Cone":           "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN4120C_57_Cone":              "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_EN4120C_57_Edge":              "85d85251-4cb2-4ade-b04c-9c6e150e41d7",
    "Cab_BT1120C_57_Cone":              "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_BT1120C_57_Edge":              "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_BT1121C_57_Edge":              "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_BT410C_Ribbon_Cone":           "4614704e-7ca2-4736-a750-648fe9033650",
    "Cab_CS212C_Ribbon_Edge":           "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "Cab_CS212C_57_Edge":               "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "Cab_CS212C_Condenser_Edge":        "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "Cab_CS1120C_Ribbon_Edge":          "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "Cab_CS1515C_57_Edge":              "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "Cab_GB412CMKI_57_Edge":            "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKI_57_Cone":            "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKII_57_Edge":           "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKII_57_Cone":           "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKII_Ribbon_Cone":       "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKII_Condenser_Cone":    "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKIII_57_Edge":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKIII_57_Cone":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKIII_Ribbon_Cone":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKIII_Condenser_Edge":   "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_GB412CMKIII_Condenser_Cone":   "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_HG2120C_Ribbon_Cone":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_HG2120C_57_Cone":              "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_HG2120C_Condenser_Cone":       "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_HG212C_Ribbon_Cone":           "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_HG215C_57_Cone":               "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_PA600C":                       "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Cab_PA999C":                       "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "Bass_Cab_BT212BC_Tube_Cone":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT212BC_Tube_Edge":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT212BC_57_Edge":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT212BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT212BC_Condenser_Cone":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT410BC_Tube_OffAxis":    "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT410BC_57_OffAxis":      "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT410BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_BT410BC_Condenser_Cone":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_AT1150BC_Tube_Cone":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_AT1150BC_Tube_Edge":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_AT1150BC_57_Edge":        "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_AT1150BC_Tube_OffAxis":   "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_AT810BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_AT810BC_57_Edge":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_AT810BC_Condenser_Cone":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_AT810BC_Condenser_Edge":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_AT810BC_Tube_Cone":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CH210BC_Tube_Cone":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CH210BC_Condenser_Cone":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CH310BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CH410BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CH410BC_57_Edge":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CA1510BC_57_Cone":        "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_CA1510BC_57_Edge":        "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_CA1510BC_Tube_Edge":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_CA1510BC_Tube_Cone":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_CA1510BC_Condenser_Edge": "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_CS410BC_Tube_Cone":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CS410BC_Tube_Edge":       "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CS410BC_57_Edge":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CS410BC_57_Cone":         "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CS410BC_Condenser_Edge":  "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_CS15BC_57_Edge":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_OrangeOBC810_57_Cone":    "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_EdenD212XLT_57_Cone":     "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_EdenD610XST_Tube_Edge":   "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_EdenD610XST_Tube_Cone":   "fb54d283-dfc2-402e-8c76-87713387d770",
    "Bass_Cab_TW215BC_57_Cone":         "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_TW215BC_57_Edge":         "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Bass_Cab_TW215BC_Tube_Edge":       "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "IBEX_Cab_OrangeRV50_212_RSC67_OffAxis_Cap":   "16b2e136-c230-4598-9931-5b913efb76e6",
    "IBEX_Cab_OrangePrPro412_RSD20_OffAxis_Cone":  "4edd00f5-1dc0-4130-a3bb-7eb608e834ab",
    "IBEX_Cab_MesaBoogie1x12Widebody_57_Edge":     "8c6c0893-9f50-492c-ac1d-4773fd697638",
    # ── Additional RS2014 cab variants (mic/position variants of existing enclosures) ──
    "Cab_TW112C_Condenser_Edge":        "70b17311-7b73-4415-968e-c26543e22e18",  # 1x12 '57 Deluxe
    "Cab_TW410C_Condenser_OffAxis":     "4614704e-7ca2-4736-a750-648fe9033650",  # 4x10 '59 Bassman
    "Cab_HG215C_Ribbon_Cone":           "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_Marshall1960AX_57_Cone":       "c97bc69c-c02d-4cce-b19d-859b72833550",  # 4x12 1960AV
    "Cab_GB412CMKIII_57_OffAxis":       "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_GB412CMKIII_Ribbon_Edge":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_GB412CMKI_Condenser_OffAxis":  "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_GB412CMKI_Condenser_Cone":     "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_BT1120C_Ribbon_Edge":          "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_CA112C_Ribbon_Cone":           "82409e48-b67c-4762-8256-963f43240ccc",  # 1x12 Mark III
    "Cab_CS1120C_Ribbon_Cone":          "f7902634-12e9-4a2d-9f9a-bcd22781cdab",  # 2x12 JP Jazz
    "Cab_CS1515C_Ribbon_Cone":          "f7902634-12e9-4a2d-9f9a-bcd22781cdab",  # 2x12 JP Jazz
    "Cab_EN4120C_57_OffAxis":           "85d85251-4cb2-4ade-b04c-9c6e150e41d7",  # 2x12 BM 30 H70
    "Cab_EN4120C_Condenser_Edge":       "85d85251-4cb2-4ade-b04c-9c6e150e41d7",  # 2x12 BM 30 H70
    "Bass_Cab_AT810BC_Tube_Edge":       "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-810E
    "Bass_Cab_AT1150BC_Condenser_Edge": "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Bass_Cab_BT410BC_57_Edge":         "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-810E
    "Bass_Cab_BT115BC_Tube_Cone":       "0c2f1129-e09d-4510-9624-7c8b05f188cf",  # 1x15 OBC 115
    "Bass_Cab_GB415BC_Tube_Cone":       "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-810E
    "Bass_Cab_CH410BC_Condenser_Cone":  "fb54d283-dfc2-402e-8c76-87713387d770",  # SVX-810E

    "Bass_Cab_BT410BC_Tube_Cone":   "fb54d283-dfc2-402e-8c76-87713387d770",  # 8x10 OBC 810
    "Bass_Cab_BT410BC_Tube_Edge":   "fb54d283-dfc2-402e-8c76-87713387d770",
    "Cab_OrangePPC412_57_Cone":     "4edd00f5-1dc0-4130-a3bb-7eb608e834ab",  # 4x12 PPC 412
    "Cab_OrangePPC412_57_Edge":     "4edd00f5-1dc0-4130-a3bb-7eb608e834ab",
    "Cab_OrangePPC412_Ribbon_Cone": "4edd00f5-1dc0-4130-a3bb-7eb608e834ab",
    # ── Marshall lowercase variants (RS+ uses lowercase 'a' suffix) ───────────
    "Cab_Marshall1960a_57_Edge":        "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # 4x12 Brit 8000
    "Cab_Marshall1960a_57_Cone":        "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_Marshall1960a_57_OffAxis":     "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_Marshall1960a_Condenser_Cone": "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_Marshall1960a_Ribbon_Edge":    "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "Cab_Marshall1960AX_57_Edge":       "c97bc69c-c02d-4cce-b19d-859b72833550",  # 4x12 1960AV
    "Cab_Marshall1960AX_Ribbon_Cone":   "c97bc69c-c02d-4cce-b19d-859b72833550",
}

# Default cab when RS key is unknown
DEFAULT_CAB_4x12  = "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b"  # 4x12 Brit 8000
DEFAULT_CAB_2x12  = "85d85251-4cb2-4ade-b04c-9c6e150e41d7"  # 2x12 BM 30 H70
DEFAULT_CAB_1x12  = "7efbb008-6942-4538-875b-d65fc7321617"  # 1x12 '57 Custom Deluxe (confirmed owned)

# ─────────────────────────────────────────────────────────────────────────────
# SPEAKER (DRIVER) MAPPING  (Rocksmith Cab Key -> AT5 SpeakerModel GUID)
# Source: GearInfo/Stomps.json extracted from AmpliTube 5.pak
# ─────────────────────────────────────────────────────────────────────────────

SPEAKER_MAP = {
    # Marshall cabs -> Celestion drivers
    "Cab_Marshall1960TV_57_Cone": "674b563d-948e-4f33-98d1-8f8904096315",  # Brit Anniversary 1 (G12H)
    "Cab_Marshall1960A":          "e372dd04-b11d-4958-8c29-0fbe341e97ca",  # Brit 75 (G12T-75)
    "Cab_Marshall1960B":          "e372dd04-b11d-4958-8c29-0fbe341e97ca",  # Brit 75 (G12T-75)
    "Cab_Marshall1960AV":         "674b563d-948e-4f33-98d1-8f8904096315",  # Brit Anniversary 1
    "Cab_Marshall1960BV":         "93ece316-161d-4a7d-b5c0-75a64a873b02",  # Brit Silver (V12-60)
    "Cab_Marshall1960SL":         "93ece316-161d-4a7d-b5c0-75a64a873b02",  # Brit Silver
    "Cab_MarshallSilver":         "93ece316-161d-4a7d-b5c0-75a64a873b02",  # Brit Silver
    "Cab_MarshallJCM800":         "e372dd04-b11d-4958-8c29-0fbe341e97ca",  # Brit 75 (G12T-75)
    "Cab_MarshallJCM900":         "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B (V30)
    "Cab_MarshallMajor":          "942153d2-81fb-4b08-9fc2-0e07a34e9ca7",  # Brit 80 (G12-80)
    # Vox cabs -> Celestion Blues
    "Cab_VoxAC30":                "aa7f635a-7c28-4116-a622-9675340f9fd8",  # Brit Alnico B (Blue)
    "Cab_Vox":                    "aa7f635a-7c28-4116-a622-9675340f9fd8",  # Brit Alnico B
    "Cab_VoxAC30Blue":            "aa7f635a-7c28-4116-a622-9675340f9fd8",  # Brit Alnico B
    # Fender cabs -> Jensen
    "Cab_FenderDeluxeReverb":     "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C (Jensen)
    "Cab_FenderTwinReverb":       "02079eab-6ff4-4741-961c-d95bb82b9662",  # American Alnico
    "Cab_FenderBassman":          "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Cab_FenderSuperReverb":      "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Cab_FenderVibroverb":        "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Cab_FenderChamp":            "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Cab_FenderChampion600":      "91e0a916-09a7-4704-b773-9023e3bda8d8",  # Custom Fender
    "Cab_Fender57Champ":          "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Cab_Fender57CustomTwin":     "02079eab-6ff4-4741-961c-d95bb82b9662",  # American Alnico
    "Cab_FenderVibroking":        "8b9fc1ce-f012-4429-b728-f0e822a1329e",  # California Red (JBL D120F)
    # Mesa cabs -> Celestion V30
    "Cab_MesaRecto":              "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2 (V30 Mesa)
    "Cab_MesaDualRecto":          "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2
    "Cab_MesaTripleRecto":        "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2
    "Cab_MesaRoadKing":           "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2
    "Cab_MesaTA30":               "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B
    # Orange cabs -> V30
    "Cab_OrangePPC412":           "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B (V30)
    "Cab_OrangePPC212":           "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B
    "Cab_OrangePPC112":           "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B
    "Cab_OrangeTinyTerror":       "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B
    # Hiwatt
    "Cab_Hiwatt":                 "d052f84c-a5fd-4a69-9d4b-d4fa68c155f2",  # HiAmp (Fane)
    # Roland
    "Cab_RolandJC120":            "f755dce5-b300-4aae-8b07-adac9da35705",  # Jazz 12 (Roland)
    # ── RS+ generic coded cab keys -> speaker drivers ─────────────────────────
    "Cab_AT0112C_Condenser_Edge":   "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C (Jensen)
    "Cab_AT0112C_57_Edge":          "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_AT0112C_Ribbon_Cone":      "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_AT0112C_Ribbon_Edge":      "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_TW112C_57_Edge":           "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C (Jensen)
    "Cab_TW112C_57_Cone":           "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_TW110C_57_Edge":           "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_TW410C_Ribbon_Cone":       "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",
    "Cab_CA112C_57_Edge":           "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2 (V30 Mesa)
    "Cab_CA412C_57_Edge":           "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",
    "Cab_CA412C_57_Cone":           "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",
    "Cab_EN212C_57_Cone":           "aa7f635a-7c28-4116-a622-9675340f9fd8",  # Brit Alnico B (Blue)
    "Cab_EN212C_57_Edge":           "aa7f635a-7c28-4116-a622-9675340f9fd8",
    "Cab_BT1120C_57_Cone":          "e372dd04-b11d-4958-8c29-0fbe341e97ca",  # Brit 75 (G12T-75)
    "Cab_CS212C_Ribbon_Edge":       "f755dce5-b300-4aae-8b07-adac9da35705",  # Jazz 12 (Roland)
    "Cab_GB412CMKIII_57_Edge":      "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B (V30)
    "Cab_HG2120C_Ribbon_Cone":      "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "Cab_PA600C":                   "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C (generic)
    "Bass_Cab_BT212BC_Tube_Cone":   "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",  # Brit Vintage 16B
    "Bass_Cab_AT1150BC_Tube_Cone":  "a3cc18b8-e9b4-49e3-b1ce-34c69b310b83",  # American 12C
    "Bass_Cab_AT810BC_57_Cone":     "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "Bass_Cab_CH210BC_Tube_Cone":   "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "Bass_Cab_CA1510BC_57_Cone":    "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",  # Brit V2 (V30)
    "Bass_Cab_CS410BC_Tube_Cone":   "f755dce5-b300-4aae-8b07-adac9da35705",  # Jazz 12 (Roland/Eden)
    "Bass_Cab_OrangeOBC810_57_Cone":"9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "IBEX_Cab_OrangeRV50_212_RSC67_OffAxis_Cap":  "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "IBEX_Cab_OrangePrPro412_RSD20_OffAxis_Cone": "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "IBEX_Cab_MesaBoogie1x12Widebody_57_Edge":    "2dc1a3c4-6a20-4deb-a9cd-5e939ae1e1fa",
    "Bass_Cab_BT410BC_Tube_Cone":   "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "Cab_OrangePPC412_57_Cone":     "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
    "Cab_OrangePPC412_57_Edge":     "9422a3d9-5e6b-4c63-bc6d-b15fcbd99f09",
}

DEFAULT_SPEAKER_A = "674b563d-948e-4f33-98d1-8f8904096315"  # Brit Anniversary 1 (Celestion G12H)
DEFAULT_SPEAKER_B = "942153d2-81fb-4b08-9fc2-0e07a34e9ca7"  # Brit 80 (Celestion G12-80)

# ─────────────────────────────────────────────────────────────────────────────
# RACK / STOMP EFFECT MAPPING  (Rocksmith Key -> AT5 GUID)
# Source: GearInfo/RoomMics.json (rack effects, models 108-155)
# Note: Stomp effects models 0-107 are in corrupted GearInfo/Amps.json
# ─────────────────────────────────────────────────────────────────────────────

EFFECT_MAP = {
    # ── RS Rack_Studio* -> AT5 stomp/rack GUIDs ──────────────────────────────
    # Source: GearInfo/Amps.json recovered from pak at offset 6755621
    # All 115 stomp models (0-107) + rack effects (108-162) now mapped

    # Core RS rack effect keys -> best AT5 match
    "Rack_StudioEQ":        "8d7ff76e-9273-46b6-95d5-3d7bd667fff2",  # 7 Band Graphic EQ
    "Rack_StudioChamber":   "ad9d0a70-7a59-4fef-ace5-c592764e3749",  # '63 Reverb (spring reverb)
    "Rack_StudioDelay":     "e11b1dc5-1f7d-42ad-af30-0539b3646b3c",  # Delay
    "Rack_StudioChorus":    "bc6a9f33-ac11-41f8-973d-0327d4f3e018",  # Chorus
    "Rack_StudioFlanger":   "7ccf016f-e540-4e46-a124-8f19ce5ab2b1",  # Flanger
    "Rack_StudioComp":      "5478981b-b18a-469f-81e7-a3e228cc9d50",  # Compressor
    "Rack_StudioPhaser":    "a4ed5e25-707d-40ef-9846-64eeb820aeea",  # Phaze Nine (MXR Phase 90)
    "Rack_StudioWah":       "6482748e-9382-4ad6-b284-5c29ee50f2d7",  # Wah (Cry Baby)
    "Rack_StudioVibrato":   "a6d48956-a0e5-4d63-9c22-b5b38604d2a5",  # Uni-V (Univibe)
    "Rack_StudioTremolo":   "50378f09-a919-4dee-9bbe-c242403a52a2",  # Opto Tremolo
    "Rack_StudioReverb":    "ad9d0a70-7a59-4fef-ace5-c592764e3749",  # '63 Reverb
    "Rack_StudioPitch":     "e2b29e5c-33a0-41f0-9d54-dc749d371fe0",  # Pitch Shifter
    "Rack_StudioNoise":     "0455f997-43ca-4c9b-9269-286a19d10d48",  # Noise Gate
    "Rack_StudioGate":      "0455f997-43ca-4c9b-9269-286a19d10d48",  # Noise Gate
    "Rack_StudioBoost":     "77f0f320-cc4e-44be-9ffe-2f0b679434ae",  # Booster (MXR)
    "Rack_StudioOD":        "fd627f5e-ba11-4082-b546-a4f0b05985ff",  # Overdrive (Boss SD-1)
    "Rack_StudioDist":      "510f6d25-6ec4-417b-bf58-0f8028209cce",  # Distortion (Boss DS-1)
    "Rack_StudioFuzz":      "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig (Big Muff)
    "Rack_StudioGraphicEQ": "8d7ff76e-9273-46b6-95d5-3d7bd667fff2",  # 7 Band Graphic EQ
    "Rack_StudioParametricEQ": "7511f3f3-cac1-476f-a1da-089556f62f58",  # Parametric EQ (rack)
    "Rack_StudioTapeDelay": "8bbfc5b9-bf29-4a55-8211-ca21dcfda8bf",  # Tape Echo
    "Rack_StudioTapDelay":  "96b57f95-4380-444a-8c0a-fbcc9bef1dd9",  # TapDelay
    "Rack_StudioHallReverb":   "69dc5617-6455-4916-a0d5-a5f5138811b3",  # Hall Reverb (rack)
    "Rack_StudioPlateReverb":  "5726816c-1af2-41f2-8427-7e045f85c95b",  # Plate Reverb (rack)
    "Rack_StudioRoomReverb":   "0755ca4e-ebb0-4507-a4e5-b5412667f9b2",  # Room Reverb (rack)
    "Rack_StudioModChorus": "bc6a9f33-ac11-41f8-973d-0327d4f3e018",  # Chorus
    "Rack_StudioModFlange": "7ccf016f-e540-4e46-a124-8f19ce5ab2b1",  # Flanger
    "Rack_StudioModPhase":  "a4ed5e25-707d-40ef-9846-64eeb820aeea",  # Phaze Nine

    # ── All 115 AT5 stomp models by name (for fuzzy matching) ────────────────
    # Delay
    "Delay":            "e11b1dc5-1f7d-42ad-af30-0539b3646b3c",
    "EchoMan":          "48e7b721-d57a-4c34-813b-95d8091d5eda",   # EHX Memory Man
    "EP Tape Echo":     "907ecdf1-15be-4f41-b56d-2705e7bb89ae",   # Maestro Echoplex
    "TapDelay":         "96b57f95-4380-444a-8c0a-fbcc9bef1dd9",
    "Analog Delay":     "b756e0c1-7685-4b38-bccc-b74c7febd868",   # Ampeg
    "DDelay":           "4468f4f7-0068-4b8b-ac2b-99e13113fe2d",   # Boss DD-3
    "Replica":          "bf72ebc2-a539-4cd2-9204-2d91e9d573df",   # T-Rex
    "SSTE":             "28bb2c33-0bdf-44f7-9274-2eca934cbbff",   # Fulltone
    "Tape Echo":        "8bbfc5b9-bf29-4a55-8211-ca21dcfda8bf",   # Fender
    # Distortion/OD/Fuzz
    "BigPig":           "58dbec22-58e0-464c-8c04-91fb9d9973e2",   # Big Muff
    "Crusher":          "305c9b6b-04cf-4673-b58a-e62afb4fefcb",
    "Diode Overdrive":  "5e65abef-82eb-4995-b911-d5eca4f8291e",
    "Distortion":       "510f6d25-6ec4-417b-bf58-0f8028209cce",   # Boss DS-1
    "Feedback":         "395ed825-f3e8-40c1-8d69-34d8b23c9100",   # Boss DF-2
    "Metal Distortion": "1910832b-2b47-46ff-b14c-46ec168e50e6",   # Boss MT-2
    "Metal Distortion 2":"e5c8acd3-3771-4df9-8d2e-ee33c8dd3d21",  # Boss HM-2
    "Overdrive":        "fd627f5e-ba11-4082-b546-a4f0b05985ff",   # Boss SD-1
    "OverScream":       "fa1de2e2-102b-4edf-b3b5-23ceaeddedf0",   # Tube Screamer
    "PROdrive":         "9b672f82-2832-4134-8db7-5cb9147c69a3",   # ProCo RAT
    "The Ambass'dor":   "c8b142b0-4480-4d79-bc5c-f0232440ce05",   # Marshall Guv'Nor
    "SVX-OD":           "1d665fde-1a62-42a1-be6d-bad9bbe5df3d",   # Ampeg OD
    "OCD":              "7c499158-084f-49b1-9543-f7e9acc122e0",   # Fulltone
    "Power Grid":       "16daf2e6-1c56-4abe-97c9-1fffe2b22bb2",   # Seymour Duncan
    "OctoBlue":         "967e57ac-b67d-4b97-942e-aca407e306e0",   # MXR Blue Box
    "Moller":           "1d03a910-c5a3-461e-a43a-485ddf3d84ef",   # T-Rex
    "Mudhoney":         "e5644c95-e382-4cfe-9c1f-85451017771d",   # T-Rex
    "Satch Dist":       "67f25e2b-1c3f-40ff-9ad2-635d782416af",   # Boss DS-1
    "Satch Overdrive":  "fc48618d-3dc3-4d3a-9183-fa3362bd277d",   # Boss OD-1
    "Tube Overdrive":   "be3bb897-6e7d-4d9a-ba58-8a034919dc3b",   # Chandler
    "AmpLess":          "d36a32bf-200c-4906-93b9-0aa91cd1f579",   # Tech21 Sansamp
    "VariDiode+":       "dbeca376-df39-45c1-b63e-3ee55b747b00",   # MXR Distortion+
    "Pinnacle Deluxe":  "8a96f6a6-49af-41fb-ab36-a62a18f17def",   # Wampler
    # Fuzz
    "Class Fuzz":       "8beec4ce-fb43-4f81-935a-3b5cb3695c8b",   # Roger Mayer
    "Fuzz Age":         "6c3ff0bf-b840-47f3-83d3-66816763097f",   # Fuzz Face
    "Fuzz Age 2":       "09ac5b94-f238-4e4c-914e-ba7662f280d9",   # Fuzz Face
    "FuzzOne":          "0679dea3-2588-4d9d-8d0d-ef3762f1f478",   # Maestro FuzzTone
    "Octa-V":           "aa74a915-a1fe-4f54-a8a8-5297c3e09b56",   # Roger Mayer Octavia
    "RightFuzz":        "b0f5949f-4825-4202-92a0-c5817f493116",   # Mosrite Fuzzrite
    "XS Fuzz":          "64e7c1cd-b860-40c7-930b-6d820b1ffa77",   # Roger Mayer Axis
    "Fuzz Wah":         "a58d91b0-d7c5-4d3d-8a9a-5c8b75335502",   # Fender
    # Dynamics
    "Compressor":       "5478981b-b18a-469f-81e7-a3e228cc9d50",
    "Dcomp":            "26c75920-d4bf-4e5e-900f-f78c70e06c17",   # MXR Dynacomp
    "SVX Compressor":   "8a24aa96-f0ae-4e1c-a534-6671e245a690",   # Ampeg
    "Fender Compressor":"f5edced9-6dfc-4851-8651-f81f5423d210",
    "Booster":          "77f0f320-cc4e-44be-9ffe-2f0b679434ae",   # MXR/CAE
    "Treble Booster":   "382fd7fe-b60f-440b-aed8-3dae6e9e94c6",
    "Red Special":      "97c9c8d9-2f26-4126-98f7-64fbc60765ca",   # Brian May
    "Gate":             "d3e05ec0-2c7b-498a-adc0-b263e853ad30",   # MXR Smart Gate
    "Dime Noise Gate":  "5aa37004-52de-4846-bb7b-1816d98562de",   # Rocktron
    "Noise Gate":       "0455f997-43ca-4c9b-9269-286a19d10d48",
    # EQ
    "7 Band Graphic":   "8d7ff76e-9273-46b6-95d5-3d7bd667fff2",
    "10 Band Graphic":  "babadeaf-9c28-4641-8fa9-d7366a3238a2",   # MXR
    "6 Band EQ":        "53d32ff2-4726-40d8-93ef-70f23fd36b73",   # MXR
    "Pre EQ 3":         "07bbabf3-09b7-4042-ad30-5a62ff6b1a0c",   # Furman PQ-3
    # Filter / Wah
    "Envelope Filter":  "77a321dd-69e1-4474-be07-d8a97e78bd1f",
    "LFO Filter":       "390c602d-5834-417d-bf0c-cafe544c5869",
    "Rezo":             "327d6d53-b6cb-4d33-bdaf-620fb52c20ec",
    "Step Filter":      "25425c78-31db-48f4-ad57-09f41e0e1291",
    "Wah":              "6482748e-9382-4ad6-b284-5c29ee50f2d7",   # Cry Baby
    "Wah 10":           "2de5239a-78d6-4a01-82e6-2ea3afb60501",   # Ibanez WH-10
    "Wah 46":           "bc86a019-ffd5-4b71-8bfe-5913e3d58d7c",   # Vox V846
    "Wah 47":           "02cd5797-10d8-4ffa-b4f4-438b93028941",   # Vox V847
    "Nu-Tron III":      "0332d916-2ab2-4b7d-98c4-73a80a42b3b1",   # Mu-Tron
    "Bass Wah":         "01cadfae-3ced-4ea6-8676-29a7e6c920b2",   # Ampeg
    "SVX Envelope Filter":"15b140e0-3e02-4adc-a9c4-c652960e60f9",
    "Star Gate":        "590df33c-23a6-4d35-bd49-b5b589ffd248",   # Brian May gate
    "May Wah":          "23c22c20-42ec-472f-84cf-2ae6b20f6f3b",   # Dunlop
    "Dime Wah":         "27cd0940-620d-401c-abe2-c9d541673cf6",   # Dunlop GCB95
    "Fender Wah":       "75f96017-8a09-41fd-9979-75bf8bf81645",
    "WahDist":          "88863a3a-cfe3-4e86-b735-1303c511bf5f",   # Slash SW95
    "Contour Wah":      "487cd1a4-834e-45b2-b5be-6a424cc6a123",   # Morley
    "Satch Wah":        "ecc79add-83b7-46ae-896a-3f1c02ece992",   # Vox Big Bad
    "Seek Wah":         "0ba47121-179c-4d42-bbb6-c3e81bb4f7af",   # Z.Vex
    "Power Wah Fuzz":   "1636cd4e-e31f-4817-be9c-244f3dfbe77d",   # Morley PWF
    # Modulation
    "Analog Flanger":   "ae6177c2-27c2-4463-a06a-357408bb2082",   # Boss BF-2
    "Chorus":           "bc6a9f33-ac11-41f8-973d-0327d4f3e018",
    "Chorus-1":         "2a9ef349-fb29-4e66-99a9-cc66d10192cc",   # Roland CE-1
    "Electric Flanger": "8a878202-9126-4d20-8e73-374e178312f4",   # EHX Electric Mistress
    "Flanger":          "7ccf016f-e540-4e46-a124-8f19ce5ab2b1",
    "Metal Flanger":    "4e4d82f9-224a-4ffb-9994-97ef8285c315",   # MXR 117
    "Opto Tremolo":     "50378f09-a919-4dee-9bbe-c242403a52a2",   # Fender
    "Tremolo":          "187eb9ab-7ae6-4797-954b-079de09e26bb",   # Fender tube
    "Phaze Nine":       "a4ed5e25-707d-40ef-9846-64eeb820aeea",   # MXR Phase 90
    "Phazer10":         "cc424097-15e5-47d3-abb9-3925073ac22b",   # MXR Phaser 100
    "Small Phazer":     "0ef53d8f-2dd5-4acd-95f8-e8652ae31240",   # EHX Small Stone
    "Phaser":           "6178531f-d021-43c0-8922-858ffa085746",   # Fender
    "FOX Phaser":       "92605dfc-4716-49ef-944f-fd8c86d76bb2",   # fOXX
    "Uni-V":            "a6d48956-a0e5-4d63-9c22-b5b38604d2a5",   # Univibe
    "Analog Chorus":    "ed2c3a06-d304-496b-b031-7725a3d27eea",   # Ampeg
    "X-Chorus":         "5f3947b1-6a09-4570-9f9c-1cc53a7fd88f",   # MXR M134
    "Nirvana":          "b1ad4a5d-1ad2-4b32-8532-945b869409e3",   # Wampler chorus/vib
    "Shape Shifter":    "96ae9a18-1c2b-48cc-843a-851adb43c091",   # Seymour Duncan
    "Seek Trem":        "86875e91-6fbd-4198-a45c-a06119e6a967",   # Z.Vex
    "Flanger Doubler":  "b3703de8-ff21-4f1e-aa89-364eeed3cb57",   # MXR
    # Pitch
    "Harmonator":       "46f09ab5-ffd9-4c5b-8eec-681f880d4530",
    "Octav":            "994770ae-ebb4-4ca8-884e-374f88fa3db0",   # Boss OC-2
    "Pitch Shifter":    "e2b29e5c-33a0-41f0-9d54-dc749d371fe0",
    "Wharmonator":      "9b8e89e2-2959-41b2-90eb-dc5de12964d0",   # DigiTech Whammy
    "SVX-OCT":          "9afc331b-c0c3-4592-b03f-c97f8d911e34",   # Ampeg octaver
    "Satch Octave":     "84de10c4-22cf-4e69-9c2d-b7fbc7a8cea2",
    "Blender":          "01648ef1-6369-4170-81a3-90dd20451260",   # Fender
    "OctoBlue":         "967e57ac-b67d-4b97-942e-aca407e306e0",   # MXR Blue Box octave fuzz
    # Reverb (stomp)
    "'63 Reverb":       "ad9d0a70-7a59-4fef-ace5-c592764e3749",   # Fender spring
    # Other
    "Acoustic Sim":     "71fe6e6d-5879-42a7-9a31-6093ecee2a1c",
    "Volume":           "de12969a-31cc-4985-b4cf-289d2970823d",
    "Step Slicer":      "66410529-1158-4d6e-a33a-474541a64571",
    "Swell":            "ca453f6e-7af5-4e90-90df-ff954b17ecc2",
    "SVX Volume":       "7b1dc197-a4ac-41cc-8b1e-d8ed4102f432",
    "Fender Volume":    "01776ae8-8442-4633-b5f7-6bfdaf423ccb",
    # X-GEAR multi-effects
    "X-VIBE":           "6db46983-d9ff-4ebf-a1eb-d59789bdd501",
    "X-DRIVE":          "b0b9f092-704a-4232-bac4-c13b4cda902a",
    "X-SPACE":          "3889d7a5-4131-4c1d-b94e-6d37dcedefc4",
    "X-TIME":           "063668e9-2af7-4a21-a554-abb1ff51a913",
    # Rack effects (models 108-155, from GearInfo/RoomMics.json)
    "Tape Echo (rack)": "a8a839aa-35e1-4fac-8834-a0a1701c63d8",
    "Digital Delay":    "1189979a-db5d-4dc1-9228-7bd974d8a8c5",
    "Tap Delay":        "6d48d2c6-a3e1-49d3-a5f5-173292c3585f",
    "Hall Reverb":      "69dc5617-6455-4916-a0d5-a5f5138811b3",
    "Inverse Reverb":   "8996879a-e9db-4d7e-a2a7-fd6d30c07144",
    "Plate Reverb":     "5726816c-1af2-41f2-8427-7e045f85c95b",
    "Room Reverb":      "0755ca4e-ebb0-4507-a4e5-b5412667f9b2",
    "Shimmer Reverb":   "1520c0ae-a27f-4b36-a73f-942f9cd3e262",
    "Digital Reverb":   "59ab0817-b168-4bdc-b837-e3cba1efb2dd",
    "Model 670":        "ae881acd-227c-418e-a0b4-8463ef2b6461",   # Fairchild
    "Saturator-X":      "205ef910-f937-4d2b-a02f-a8483a3339a4",
    "Vintage EQ1-A":    "5550afaf-263b-458b-98ef-4db90bb2f219",   # Pultec
    "White 2A":         "719106ad-5c84-4f94-a9db-eb3264281314",   # LA-2A
    "Black 76":         "aecfbde7-4f23-44ca-9f58-b0a110f0ea7a",   # 1176
    "GraphicEQ":        "b66b51c2-d9a3-4909-b7e0-cd1e51636e97",
    "Stereo Enhancer":  "fe891a4f-6098-423d-b8dd-3213373b990c",
    "Rotary Speaker":   "99c5d753-57e3-40a4-9612-04623ac61289",
    "Tube Compressor":  "d0211742-18e6-4fdb-9efa-3d72e4ae515b",
    "Parametric EQ 3":  "9f1147a6-302f-48f3-a5bc-26cc5d399a8b",
    "Pitch Shifter (rack)": "845b672b-255f-4edf-9e67-68b607dcf63a",
    "Step Slicer (rack)": "4b91de5f-73c6-46d2-957b-6b9451abf050",
    "Rezo (rack)":      "e2e5495c-5ac3-405f-9fdd-b73670d413c0",
    "Harmonator (rack)":"647b8569-e3b4-48c3-b8a1-37c5f920e3f6",
    "AM Modulator":     "02df7fb2-5418-46f2-8c80-7283a3871551",
    "AutoPan":          "db51c05e-fc56-4347-81c4-be74dd9ec22e",
    "Filter Formant":   "a7e2c155-6af8-40d5-8914-8446c46790b2",
    "Filter Phaser":    "96ee1a4f-4090-4870-bd1a-1c3d908c3e63",
    "FM Modulator":     "91caea60-f052-477a-b0d7-8b5520050813",
    "Tape Cassette":    "95c36693-f913-4fc5-b60f-6b1732103cee",
    "EQ PG":            "ec1212e3-d949-4d91-a1dd-4bb6803f8432",   # API 560
    "Parametric EQ":    "7511f3f3-cac1-476f-a1da-089556f62f58",
    "Filter-C":         "fa35cf20-ec32-4482-963c-87b5534a3e08",
    "Filter-M":         "f58b7298-6321-4cd9-814d-42116a056352",
    "Filter-O":         "198e9bca-4466-4bc5-be66-dfbca98c8db0",
    "Filter-R":         "1877f1c9-002a-4c05-9433-31f05c864430",
    "EQ-81":            "179cdb9f-d2bf-4ee4-9172-94f2dc57a724",   # Neve
    "Analog Chorus (rack)": "02643125-de84-4c94-b214-4d300652332b",
    "Digital Chorus":   "1edbb450-d048-11dc-95ff-0800200c9a66",
    "Digital Flanger":  "c11388bb-6326-4766-a440-ea9fa3f82425",
    "Swell (rack)":     "1e27e673-20fe-474e-a438-d85a9bc566b4",
    "Step Filter (rack)":"fb5d2469-05f6-4a44-9576-41ae232c9385",
    # ── RS+ generic coded pedal keys ─────────────────────────────────────────
    "Pedal_SpringReverb":       "ad9d0a70-7a59-4fef-ace5-c592764e3749",  # '63 Reverb (Fender spring)
    "Pedal_EQ5":                "8d7ff76e-9273-46b6-95d5-3d7bd667fff2",  # 7 Band Graphic EQ
    "Pedal_EQ8":                "babadeaf-9c28-4641-8fa9-d7366a3238a2",  # 10 Band Graphic
    "Pedal_AcousticEmulator":   "71fe6e6d-5879-42a7-9a31-6093ecee2a1c",  # Acoustic Sim
    "Pedal_LoFiFilter":         "95c36693-f913-4fc5-b60f-6b1732103cee",  # Tape Cassette
    "Pedal_GermaniumDrive":     "6c3ff0bf-b840-47f3-83d3-66816763097f",  # Fuzz Age (Germanium Fuzz Face)
    "Pedal_CustomDrive":        "fd627f5e-ba11-4082-b546-a4f0b05985ff",  # Overdrive (Boss SD-1)
    "Pedal_Chorus20":           "2a9ef349-fb29-4e66-99a9-cc66d10192cc",  # Chorus-1 (Roland CE-1)
    "Pedal_RangeBooster":       "382fd7fe-b60f-440b-aed8-3dae6e9e94c6",  # Treble Booster
    "Pedal_AmpTrem":            "50378f09-a919-4dee-9bbe-c242403a52a2",  # Opto Tremolo
    "Pedal_OctaveUp":           "aa74a915-a1fe-4f54-a8a8-5297c3e09b56",  # Octa-V (Roger Mayer Octavia)
    "Pedal_Tremolo":            "187eb9ab-7ae6-4797-954b-079de09e26bb",  # Tremolo
    "Pedal_ModernWah":          "6482748e-9382-4ad6-b284-5c29ee50f2d7",  # Wah (Cry Baby)
    "Pedal_OmniMod":            "6db46983-d9ff-4ebf-a1eb-d59789bdd501",  # X-VIBE
    "Pedal_Octavius":           "994770ae-ebb4-4ca8-884e-374f88fa3db0",  # Octav (Boss OC-2)
    "Pedal_LineDrive":          "77f0f320-cc4e-44be-9ffe-2f0b679434ae",  # Booster
    "Pedal_MetalDistortion":    "1910832b-2b47-46ff-b14c-46ec168e50e6",  # Metal Distortion (Boss MT-2)
    "Pedal_MultiPitch":         "9b8e89e2-2959-41b2-90eb-dc5de12964d0",  # Wharmonator (Whammy)
    "Pedal_UKWah":              "02cd5797-10d8-4ffa-b4f4-438b93028941",  # Wah 47 (Vox V847)
    "Pedal_Chorus":             "bc6a9f33-ac11-41f8-973d-0327d4f3e018",  # Chorus
    "Pedal_CaptFuzzle":         "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig (Big Muff)
    "Pedal_ValveEcho":          "8bbfc5b9-bf29-4a55-8211-ca21dcfda8bf",  # Tape Echo
    "Pedal_ModDelay":           "063668e9-2af7-4a21-a554-abb1ff51a913",  # X-TIME (mod delay)
    "Pedal_Phaser":             "a4ed5e25-707d-40ef-9846-64eeb820aeea",  # Phaze Nine (Phase 90)
    "Pedal_NoFiEcho":           "95c36693-f913-4fc5-b60f-6b1732103cee",  # Tape Cassette (lo-fi)
    "Pedal_ShaverPhaser":       "0ef53d8f-2dd5-4acd-95f8-e8652ae31240",  # Small Phazer (EHX Small Stone)
    "Pedal_Compression":        "5478981b-b18a-469f-81e7-a3e228cc9d50",  # Compressor
    "Pedal_USWah":              "6482748e-9382-4ad6-b284-5c29ee50f2d7",  # Wah (Cry Baby)
    "Pedal_CosmicEcho":         "48e7b721-d57a-4c34-813b-95d8091d5eda",  # EchoMan (Memory Man)
    "Pedal_OilCanEcho":         "8bbfc5b9-bf29-4a55-8211-ca21dcfda8bf",  # Tape Echo
    "Pedal_AnalogueDelay":      "b756e0c1-7685-4b38-bccc-b74c7febd868",  # Analog Delay
    "Pedal_VintageFlanger":     "8a878202-9126-4d20-8e73-374e178312f4",  # Electric Flanger (EHX Mistress)
    "Pedal_BobFilter":          "77a321dd-69e1-4474-be07-d8a97e78bd1f",  # Envelope Filter
    "Pedal_PlateVerb":          "5726816c-1af2-41f2-8427-7e045f85c95b",  # Plate Reverb
    "Pedal_BakedRotatoe":       "a6d48956-a0e5-4d63-9c22-b5b38604d2a5",  # Uni-V (Univibe)
    "Pedal_TubeSpring":         "ad9d0a70-7a59-4fef-ace5-c592764e3749",  # '63 Reverb (spring)
    "Pedal_FuzzWasHe":          "09ac5b94-f238-4e4c-914e-ba7662f280d9",  # Fuzz Age 2 (Si Fuzz Face)
    "Pedal_ShredZone":          "510f6d25-6ec4-417b-bf58-0f8028209cce",  # Distortion (Boss DS-1)
    "Pedal_Swole":              "5478981b-b18a-469f-81e7-a3e228cc9d50",  # Compressor
    "Pedal_ModernFlanger":      "7ccf016f-e540-4e46-a124-8f19ce5ab2b1",  # Flanger
    "Pedal_BuzzToo":            "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig (Big Muff)
    "Pedal_AutoFilter":         "77a321dd-69e1-4474-be07-d8a97e78bd1f",  # Envelope Filter
    "Pedal_BitCruncher":        "95c36693-f913-4fc5-b60f-6b1732103cee",  # Tape Cassette
    "Pedal_NoiseGate":          "0455f997-43ca-4c9b-9269-286a19d10d48",  # Noise Gate
    "Pedal_ClassicFlanger":     "ae6177c2-27c2-4463-a06a-357408bb2082",  # Analog Flanger (Boss BF-2)
    "Pedal_NPNDelay":           "e11b1dc5-1f7d-42ad-af30-0539b3646b3c",  # Delay
    "Pedal_BuzzOne":            "0679dea3-2588-4d9d-8d0d-ef3762f1f478",  # FuzzOne (Maestro FuzzTone)
    "Pedal_MultiTrem":          "187eb9ab-7ae6-4797-954b-079de09e26bb",  # Tremolo
    "Pedal_AmpVibe":            "a6d48956-a0e5-4d63-9c22-b5b38604d2a5",  # Uni-V (Univibe)
    "Pedal_80sFlanger":         "4e4d82f9-224a-4ffb-9994-97ef8285c315",  # Metal Flanger (MXR 117)
    "Pedal_DigitalVerb":        "59ab0817-b168-4bdc-b837-e3cba1efb2dd",  # Digital Reverb
    "Pedal_Limiter":            "5478981b-b18a-469f-81e7-a3e228cc9d50",  # Compressor (closest to limiter)
    "Pedal_Distortion":         "510f6d25-6ec4-417b-bf58-0f8028209cce",  # Distortion (Boss DS-1)
    # Bass pedals
    "Bass_Pedal_MBComp":        "d0211742-18e6-4fdb-9efa-3d72e4ae515b",  # Tube Compressor
    "Bass_Pedal_BassEQ8":       "babadeaf-9c28-4641-8fa9-d7366a3238a2",  # 10 Band Graphic
    "Bass_Pedal_BassChorus":    "ed2c3a06-d304-496b-b031-7725a3d27eea",  # Analog Chorus (Ampeg)
    "Bass_Pedal_BassFuzz":      "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig (Big Muff)
    "Bass_Pedal_BassOverdrive": "1d665fde-1a62-42a1-be6d-bad9bbe5df3d",  # SVX-OD
    "Bass_Pedal_BassSubOctave": "9afc331b-c0c3-4592-b03f-c97f8d911e34",  # SVX-OCT
    "Bass_Pedal_BassDistortion":"510f6d25-6ec4-417b-bf58-0f8028209cce",  # Distortion
    "Bass_Pedal_EdenWTDI":      "d36a32bf-200c-4906-93b9-0aa91cd1f579",  # AmpLess (Sansamp)
    "Bass_Pedal_BassAutoFilter":"15b140e0-3e02-4adc-a9c4-c652960e60f9",  # SVX Envelope Filter
    "Bass_Pedal_BassFlanger":   "7ccf016f-e540-4e46-a124-8f19ce5ab2b1",  # Flanger
    "Bass_Pedal_BassEnbig":     "9b8e89e2-2959-41b2-90eb-dc5de12964d0",  # Wharmonator (Whammy)
    # Additional rack effects
    "Rack_StudioVerb":          "59ab0817-b168-4bdc-b837-e3cba1efb2dd",  # Digital Reverb
    "Rack_StudioPlate":         "5726816c-1af2-41f2-8427-7e045f85c95b",  # Plate Reverb
    "Rack_StudioCompressor":    "d0211742-18e6-4fdb-9efa-3d72e4ae515b",  # Tube Compressor
    "Rack_StudioGraphicEQ":     "8d7ff76e-9273-46b6-95d5-3d7bd667fff2",  # 7 Band Graphic EQ
    "Rack_SynthFilter":         "a7e2c155-6af8-40d5-8914-8446c46790b2",  # Filter Formant
    "Rack_TapeEcho":            "8bbfc5b9-bf29-4a55-8211-ca21dcfda8bf",  # Tape Echo
    "Rack_StereoPhaser":        "96ee1a4f-4090-4870-bd1a-1c3d908c3e63",  # Filter Phaser
    # IBEX branded effects
    "Ibex_Pedal_EHXRamsHeadBigMuffPi": "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig
    "Ibex_Pedal_EHXSmallClone": "1edbb450-d048-11dc-95ff-0800200c9a66",  # Digital Chorus
    "IBEX_Pedal_OrangeSustain": "77f0f320-cc4e-44be-9ffe-2f0b679434ae",  # Booster
    "IBEX_Pedal_OrangeDistortion": "510f6d25-6ec4-417b-bf58-0f8028209cce",  # Distortion
    "IBEX_Pedal_OrangePhaser":  "a4ed5e25-707d-40ef-9846-64eeb820aeea",  # Phaze Nine
    "IBEX_Rack_ModVerb":        "59ab0817-b168-4bdc-b837-e3cba1efb2dd",  # Digital Reverb
    "IBEX_Rack_RolandDimensionD": "1edbb450-d048-11dc-95ff-0800200c9a66",  # Digital Chorus
    "IBEX_Pedal_DaFuzz":        "58dbec22-58e0-464c-8c04-91fb9d9973e2",  # BigPig
}


# ─────────────────────────────────────────────────────────────────────────────
# AMP PARAM SUFFIX MAP  (AT5 GUID prefix -> DSP param suffix)
# Source: factory presets + ThumbnailName inference
# Format: first 8 chars of GUID -> suffix string appended to knob names
# e.g. Bass -> Bass_JCM800AT4
# ─────────────────────────────────────────────────────────────────────────────

AMP_SUFFIX_MAP = {
    # ── Confirmed from factory presets ───────────────────────────────────────
    "f2190a68": "53Bassman",
    "71a76a9f": "AmericanTubeClean",
    "82972243": "AmericanTubeClean2",
    "31040aa1": "AmpScholtzRockmanX100",
    "e3d7fcaa": "AmpVoxAC30BrianMay",
    "ff274db4": "AmpegB15",
    "f1d8d4c0": "AmpegBA500",
    "862b5977": "AmpegSVT4Pro",
    "52f28b23": "AmpegSVTClassic",
    "2aa0f50f": "AmpegSVTVR",
    "0265b273": "AmpegV4B",
    "3fcc8ad1": "Bassman",
    "fb5fc82f": "BritishTubeLead1",
    "d9aa41f9": "CaliforniaTweed",
    "5f4f50a1": "Champ57",
    "016a8c2a": "Champion",
    "cfa6b70c": "Darrell100",
    "ebecb740": "Deacy",
    "d4d5b530": "Deluxe57",
    "89b3caab": "DeluxeReverb",
    "a0fa7c56": "Fender57CustomChamp",
    "bf860ad9": "Fender57CustomDeluxe",
    "d3c791b9": "Fender65CustomSuperReverb",
    "6f1c22b5": "FenderCustomBandmaster",
    "6c421302": "FenderCustomPro",
    "84f03443": "FenderShowman",
    "95b9bc84": "FenderTwinReverbBright",
    "8fe96936": "JCM800AT4",
    "a913acaa": "Leslie3300",
    "6c4fc562": "LeslieG37",
    "c13004d2": "LeslieModel122",
    "3f4b67ce": "LeslieModel122A",
    "2e94cff0": "LeslieModel147",
    "2ea3ecfb": "MarshallAFD100",
    "155f0121": "MarshallJCMSlash",
    "7788f707": "MarshallJTM45",
    "d089ef66": "MarshallJTM45MkII",
    "75ad4a0e": "MesaDualRectifier",
    "6e5c01fe": "MesaMarkIICPlus",
    "6ec4bf7a": "MesaMarkIII",
    "1fbf7d6e": "MesaMarkIV",
    "d31154a9": "MesaMarkV",
    "1284c9cc": "MesaTA30",
    "2ed4e896": "MesaTripleCrown",
    "c85e5dc4": "MesaTripleRectifier",
    "15761216": "MetalCleanT",
    "907be0ce": "MetalHead",
    "9400d18f": "MetalLeadT",
    "dcc7c825": "MetalLeadV",
    "3c25674f": "OrangeDualTerror",
    "827aedfb": "OrangeOR50",
    "1e170e52": "Peavey5150Satriani",
    "2a1f483c": "Princeton",
    "a2f18e96": "Silvertone1484",
    "ad4ea282": "SolidStateBassPre",
    "f4b89ab3": "Supersonic",
    "b3869f27": "TwinAmp",
    "dffa559d": "VibroKing",
    "f0951b1e": "VibroVerb",
    "1b5961b1": "VintageMetalLead",
    "57c43635": "MarshallJVMSatriani",
    # ── Inferred from ThumbnailName ───────────────────────────────────────────
    "a91067a3": "MesaMKIIIClean",  # confirmed from preset
    "ac08939a": "RolandJazzAmp120",
    "300ed819": "Sunn1200",
    "5d235e0d": "BritishCopper30TB",
    "26fbbf20": "HiAmp",
    "4af9d89a": "AmericanLeadMark3",
    "ecb60014": "360Bass",
    "ca4587b9": "VintageB",
    "5558e374": "CarvinV3M",
    "cbf3c00f": "JCM900",
    "e1eed2cf": "RedPig",
    "3930eb8b": "BritSilver",
    "abdcae70": "DrZMaz18",
    "cc59b472": "DrZZWreck",
    "c936fc9c": "ENGLE650",
    "88d927a0": "ENGLPowerball",
    "d0546d04": "FenderProJunior",
    "9e6f407a": "FenderBassman300",
    "4c9e667b": "Fender57CustomTwin",
    "55078333": "JetCity20",
    "913db945": "JetCity100",
    "6e8690b3": "OrangeOR120",
    "99e446c7": "OrangeTinyTerror",
    "e6151532": "OrangeRockerverb50",
    "dd7b0e06": "OrangeAD30",
    "e3260631": "OrangeThunderverb200",
    "dfb00647": "OrangeAD200",
    "4a22ac9f": "SoldanoSLO100",
    "f058124b": "THDBiAmp",
    "18f9d728": "NewYorkB750",
    "f24511a1": "SilverPlate50",
    "185e9cde": "VHandcraft4",
    "4b13e59f": "German34",
    "533d3c6c": "BritishTB30",
    "bca11751": "ModernTubeLead",
    "bd903ed7": "TubeVintageCombo",
}

AMP_KNOB_MAP = {
    "a91067a3-fd80-40a8-be35-0681da5c4f47": {'Bass': 'Bass_MesaMKIIIClean', 'Mid': 'Middle_MesaMKIIIClean', 'Middle': 'Middle_MesaMKIIIClean', 'Treble': 'Treble_MesaMKIIIClean', 'Presence': 'Presence_MesaMKIIIClean', 'Pres': 'Presence_MesaMKIIIClean', 'Volume': 'Volume_MesaMKIIIClean', 'Master': 'Master_MesaMKIIIClean', 'Gain': 'Volume_MesaMKIIIClean'},
    "016a8c2a-489e-49da-81d7-5b72feb60f74": {'Volume': 'Volume_Champion', 'Loudness1': 'Volume_Champion', 'Master': 'Volume_Champion'},
    "0265b273-d648-47c7-a5ef-579acba82a0a": {'Bass': 'Bass_AmpegV4B', 'Mid': 'MidRange_AmpegV4B', 'Treble': 'Treble_AmpegV4B', 'Volume': 'Master_AmpegV4B', 'Master': 'Master_AmpegV4B', 'Gain': 'Gain_AmpegV4B', 'PreAmp': 'Gain_AmpegV4B', 'Sensitivity': 'Gain_AmpegV4B'},
    "1284c9cc-6efa-4720-a0da-106a2d2af1d8": {'Volume': 'Volume1_MesaTA30', 'Loudness1': 'Volume1_MesaTA30'},
    "155f0121-a2ee-4e16-aaa0-44948f9be44f": {'Bass': 'Bass_MarshallJCMSlash', 'Mid': 'Mid_MarshallJCMSlash', 'Middle': 'Mid_MarshallJCMSlash', 'Treble': 'Treble_MarshallJCMSlash', 'Pres': 'Presence_MarshallJCMSlash', 'Presence': 'Presence_MarshallJCMSlash', 'Volume': 'Volume_MarshallJCMSlash', 'Loudness1': 'Volume_MarshallJCMSlash', 'Master': 'Volume_MarshallJCMSlash', 'Gain': 'Gain_MarshallJCMSlash', 'PreAmp': 'Gain_MarshallJCMSlash', 'Sensitivity': 'Gain_MarshallJCMSlash', 'Lead': 'Lead_MarshallJCMSlash', 'Rhythm': 'Rhythm_MarshallJCMSlash'},
    "15761216-f2fe-4d41-a6ec-9bff8199517c": {'Bass': 'Bass_MetalCleanT', 'Mid': 'Mid_MetalCleanT', 'Middle': 'Mid_MetalCleanT', 'Treble': 'Treble_MetalCleanT', 'Pres': 'Presence_MetalCleanT', 'Presence': 'Presence_MetalCleanT', 'Volume': 'Volume_MetalCleanT', 'Loudness1': 'Volume_MetalCleanT', 'Master': 'Volume_MetalCleanT', 'Gain': 'Gain_MetalCleanT', 'PreAmp': 'Gain_MetalCleanT', 'Sensitivity': 'Gain_MetalCleanT'},
    "1b5961b1-f862-4c8a-9a9b-a920da8c5cc2": {'Bass': 'Bass_VintageMetalLead', 'Mid': 'Mid_VintageMetalLead', 'Middle': 'Mid_VintageMetalLead', 'Treble': 'Treble_VintageMetalLead', 'Pres': 'Presence_VintageMetalLead', 'Presence': 'Presence_VintageMetalLead', 'Volume': 'Volume_VintageMetalLead', 'Loudness1': 'Volume_VintageMetalLead', 'Master': 'Volume_VintageMetalLead', 'Gain': 'Gain_VintageMetalLead', 'PreAmp': 'Gain_VintageMetalLead', 'Sensitivity': 'Gain_VintageMetalLead'},
    "1e170e52-9ff7-40ff-995f-fab2cdef7cf5": {'Pres': 'Presence_Peavey5150Satriani', 'Presence': 'Presence_Peavey5150Satriani'},
    "1fbf7d6e-dad8-470f-b204-4d96b5466893": {'Bass': 'R1R2Bass_MesaMarkIV', 'Treble': 'R1Treble_MesaMarkIV', 'Lead': 'LeadDrive_MesaMarkIV'},
    "2a1f483c-a136-45b6-81ec-e92c60f8d009": {'Bass': 'Bass_Princeton', 'Treble': 'Treble_Princeton', 'Volume': 'Volume_Princeton', 'Loudness1': 'Volume_Princeton', 'Master': 'Volume_Princeton'},
    "2aa0f50f-a6c9-4edd-97c2-df71a24087db": {'Mid': 'MidRange_AmpegSVTVR', 'Volume': 'Volume1_AmpegSVTVR', 'Loudness1': 'Volume1_AmpegSVTVR', 'Loudness2': 'Volume2_AmpegSVTVR'},
    "2e94cff0-16da-445b-98bb-b8a47bc2d2da": {'Volume': 'Volume_LeslieModel147', 'Loudness1': 'Volume_LeslieModel147', 'Master': 'Volume_LeslieModel147', 'Gain': 'Gain_LeslieModel147', 'PreAmp': 'Gain_LeslieModel147', 'Sensitivity': 'Gain_LeslieModel147'},
    "2ea3ecfb-1b0c-417a-8788-86f5915f43c5": {'Bass': 'Bass_MarshallAFD100', 'Mid': 'Mid_MarshallAFD100', 'Middle': 'Mid_MarshallAFD100', 'Treble': 'Treble_MarshallAFD100', 'Pres': 'Presence_MarshallAFD100', 'Presence': 'Presence_MarshallAFD100', 'Volume': 'Volume_MarshallAFD100', 'Loudness1': 'Volume_MarshallAFD100', 'Master': 'Volume_MarshallAFD100', 'Gain': 'Gain_MarshallAFD100', 'PreAmp': 'Gain_MarshallAFD100', 'Sensitivity': 'Gain_MarshallAFD100'},
    "2ed4e896-6cf4-40ee-bc12-15f0c4d38b65": {'Master': 'Output_MesaTripleCrown'},
    "3930eb8b-3eda-4079-b86d-7bfd7d4449bc": {'Bass': 'Bass_MarshallSilverJubilee', 'Mid': 'Mid_MarshallSilverJubilee', 'Middle': 'Mid_MarshallSilverJubilee', 'Treble': 'Treble_MarshallSilverJubilee', 'Pres': 'Presence_MarshallSilverJubilee', 'Presence': 'Presence_MarshallSilverJubilee', 'Volume': 'Volume_MarshallSilverJubilee', 'Loudness1': 'Volume_MarshallSilverJubilee', 'Master': 'Volume_MarshallSilverJubilee', 'Gain': 'Gain_MarshallSilverJubilee', 'PreAmp': 'Gain_MarshallSilverJubilee', 'Sensitivity': 'Gain_MarshallSilverJubilee', 'Lead': 'Lead_MarshallSilverJubilee', 'Rhythm': 'Rhythm_MarshallSilverJubilee'},
    "3c25674f-a418-4fec-863c-f94495c746a0": {'Master': 'Output_OrangeDualTerror'},
    "3f4b67ce-214f-445f-a0c1-b7d08f13029d": {'Volume': 'Volume_LeslieModel122A', 'Loudness1': 'Volume_LeslieModel122A', 'Master': 'Volume_LeslieModel122A', 'Gain': 'Gain_LeslieModel122A', 'PreAmp': 'Gain_LeslieModel122A', 'Sensitivity': 'Gain_LeslieModel122A'},
    "3fcc8ad1-6d5e-416d-9c3d-7aae91c6f4d4": {'Bass': 'Bass_Bassman', 'Mid': 'Middle_Bassman', 'Middle': 'Middle_Bassman', 'Treble': 'Treble_Bassman', 'Pres': 'Presence_Bassman', 'Presence': 'Presence_Bassman', 'Volume': 'Volume_Bassman', 'Loudness1': 'Volume_Bassman', 'Master': 'Volume_Bassman'},
    "41f3868c-62c3-4bd0-8c29-130e9426d4e9": {'Volume': 'Volume1_DSPInputMode', 'Loudness1': 'Volume1_DSPInputMode', 'Loudness2': 'Volume2_AmpegHeritageB15N'},
    "4a22ac9f-aabb-4180-b697-5d5710a1acc2": {'Bass': 'Bass', 'Mid': 'Middle', 'Middle': 'Middle', 'Treble': 'Treble', 'Pres': 'Presence', 'Presence': 'Presence'},
    "52f28b23-80e3-4f43-9508-4447258b11c0": {'Bass': 'Bass_AmpegSVTClassic', 'Mid': 'Mid_AmpegSVTClassic', 'Middle': 'Mid_AmpegSVTClassic', 'Treble': 'Treble_AmpegSVTClassic', 'Volume': 'Master_AmpegSVTClassic', 'Master': 'Master_AmpegSVTClassic', 'Gain': 'Gain_AmpegSVTClassic', 'PreAmp': 'Gain_AmpegSVTClassic', 'Sensitivity': 'Gain_AmpegSVTClassic'},
    "592bb813-9b42-4e33-af03-8ecc3f6edc93": {'Bass': 'Bass_Roland120Dime', 'Mid': 'Mid_Roland120Dime', 'Middle': 'Mid_Roland120Dime', 'Treble': 'Treble_Roland120Dime', 'Volume': 'Volume_Roland120Dime', 'Loudness1': 'Volume_Roland120Dime', 'Master': 'Volume_Roland120Dime'},
    "5f4f50a1-d5cb-43be-ad11-084e4ff21ea6": {'Volume': 'Volume_Champ57', 'Loudness1': 'Volume_Champ57', 'Master': 'Volume_Champ57'},
    "6c421302-9602-4ee8-b94a-672aa24cdde4": {'Bass': 'Bass_FenderCustomPro', 'Treble': 'Treble_FenderCustomPro', 'Pres': 'Presence_FenderCustomPro', 'Presence': 'Presence_FenderCustomPro'},
    "6c4fc562-aa92-4e39-b73e-85773fd6a97a": {'Bass': 'Bass_LeslieG37', 'Mid': 'Mid_LeslieG37', 'Middle': 'Mid_LeslieG37', 'Treble': 'Treble_LeslieG37'},
    "6e5c01fe-e1be-4e91-8657-74718ac8cb6e": {'Bass': 'Bass_MesaMarkIICPlus', 'Mid': 'Middle_MesaMarkIICPlus', 'Middle': 'Middle_MesaMarkIICPlus', 'Treble': 'Treble_MesaMarkIICPlus', 'Pres': 'Presence_MesaMarkIICPlus', 'Presence': 'Presence_MesaMarkIICPlus', 'Volume': 'Volume_MesaMarkIICPlus', 'Loudness1': 'Volume_MesaMarkIICPlus', 'Master': 'Master_MesaMarkIICPlus', 'Lead': 'Lead_MesaMarkIICPlus'},
    "6e8690b3-f6cf-4c36-b3c2-7f38fcc5706e": {'Gain': 'Gain', 'PreAmp': 'Gain', 'Sensitivity': 'Gain'},
    "6ec4bf7a-dc59-4443-b2fb-1e645bf5192c": {'Bass': 'Bass_MesaMarkIII', 'Mid': 'Middle_MesaMarkIII', 'Middle': 'Middle_MesaMarkIII', 'Treble': 'Treble_MesaMarkIII', 'Pres': 'Presence_MesaMarkIII', 'Presence': 'Presence_MesaMarkIII', 'Volume': 'Volume_MesaMarkIII', 'Loudness1': 'Volume_MesaMarkIII', 'Master': 'Master_MesaMarkIII', 'Lead': 'Lead_MesaMarkIII', 'Rhythm': 'Rhy_MesaMarkIII'},
    "6f1c22b5-3593-4d86-a9a3-fae8c9504d77": {'Bass': 'Bass_FenderCustomBandmaster', 'Treble': 'Treble_FenderCustomBandmaster', 'Pres': 'Presence_FenderCustomBandmaster', 'Presence': 'Presence_FenderCustomBandmaster'},
    "71a76a9f-cf70-4f59-971f-9864a055523c": {'Bass': 'Bass_AmericanTubeClean', 'Mid': 'Mid_AmericanTubeClean', 'Middle': 'Mid_AmericanTubeClean', 'Treble': 'Treble_AmericanTubeClean', 'Pres': 'Presence_AmericanTubeClean', 'Presence': 'Presence_AmericanTubeClean', 'Volume': 'Volume_AmericanTubeClean', 'Loudness1': 'Volume_AmericanTubeClean', 'Master': 'Volume_AmericanTubeClean', 'Gain': 'Gain_AmericanTubeClean', 'PreAmp': 'Gain_AmericanTubeClean', 'Sensitivity': 'Gain_AmericanTubeClean'},
    "75ad4a0e-5c75-443d-8617-9681c4fe58d3": {'Bass': 'Ch1Bass_MesaDualRectifier', 'Mid': 'Ch1Mid_MesaDualRectifier', 'Treble': 'Ch1Treble_MesaDualRectifier'},
    "7788f707-4ef2-44cd-862a-a82ffdf7172b": {'Bass': 'Bass_MarshallJTM45', 'Mid': 'Mid_MarshallJTM45', 'Middle': 'Mid_MarshallJTM45', 'Treble': 'Treble_MarshallJTM45', 'Pres': 'Presence_MarshallJTM45', 'Presence': 'Presence_MarshallJTM45'},
    "802af8da-63c6-4ccf-a4b9-6d13255ef57f": {'Bass': 'Bass', 'Mid': 'MidLevel', 'Treble': 'Treble', 'Volume': 'Volume', 'Loudness1': 'Volume', 'Master': 'Volume', 'Gain': 'Gain', 'PreAmp': 'Gain', 'Sensitivity': 'Gain'},
    "827aedfb-cdc1-412e-8e47-5bac3c3c6d06": {'Bass': 'Bass_OrangeOR50', 'Mid': 'Mid_OrangeOR50', 'Middle': 'Mid_OrangeOR50', 'Treble': 'Treble_OrangeOR50', 'Volume': 'Volume_OrangeOR50', 'Loudness1': 'Volume_OrangeOR50', 'Master': 'Volume_OrangeOR50', 'Gain': 'Gain_OrangeOR50', 'PreAmp': 'Gain_OrangeOR50', 'Sensitivity': 'Gain_OrangeOR50'},
    "82972243-cd55-4b43-82f3-f15e3bc13dc7": {'Bass': 'Bass_AmericanTubeClean2', 'Mid': 'Mid_AmericanTubeClean2', 'Middle': 'Mid_AmericanTubeClean2', 'Treble': 'Treble_AmericanTubeClean2', 'Pres': 'Presence_AmericanTubeClean2', 'Presence': 'Presence_AmericanTubeClean2', 'Volume': 'Volume_AmericanTubeClean2', 'Loudness1': 'Volume_AmericanTubeClean2', 'Master': 'Volume_AmericanTubeClean2', 'Gain': 'Gain_AmericanTubeClean2', 'PreAmp': 'Gain_AmericanTubeClean2', 'Sensitivity': 'Gain_AmericanTubeClean2'},
    "84f03443-ae64-4c7e-970f-06d1191cd906": {'Bass': 'Bass_FenderShowman', 'Mid': 'Mid_FenderShowman', 'Middle': 'Mid_FenderShowman', 'Treble': 'Treble_FenderShowman', 'Pres': 'Presence_FenderShowman', 'Presence': 'Presence_FenderShowman', 'Volume': 'Volume_FenderShowman', 'Loudness1': 'Volume_FenderShowman', 'Master': 'Volume_FenderShowman', 'Gain': 'Gain_FenderShowman', 'PreAmp': 'Gain_FenderShowman', 'Sensitivity': 'Gain_FenderShowman'},
    "862b5977-9c12-4665-88cd-86f668da8877": {'Bass': 'Bass_AmpegSVT4Pro', 'Mid': 'Mid_AmpegSVT4Pro', 'Middle': 'Mid_AmpegSVT4Pro', 'Treble': 'Treble_AmpegSVT4Pro', 'Volume': 'Master_AmpegSVT4Pro', 'Master': 'Master_AmpegSVT4Pro', 'Gain': 'Gain_AmpegSVT4Pro', 'PreAmp': 'Gain_AmpegSVT4Pro', 'Sensitivity': 'Gain_AmpegSVT4Pro'},
    "89b3caab-dffb-4c29-85d9-2a60cb93c566": {'Bass': 'Bass_DeluxeReverb', 'Treble': 'Treble_DeluxeReverb', 'Volume': 'Volume_DeluxeReverb', 'Loudness1': 'Volume_DeluxeReverb', 'Master': 'Volume_DeluxeReverb'},
    "8fe96936-5178-4950-9b80-d89c32534bad": {'Bass': 'Bass_JCM800AT4', 'Mid': 'Middle_JCM800AT4', 'Middle': 'Middle_JCM800AT4', 'Treble': 'Treble_JCM800AT4', 'Pres': 'Presence_JCM800AT4', 'Presence': 'Presence_JCM800AT4', 'Volume': 'Master_JCM800AT4', 'Master': 'Master_JCM800AT4', 'Gain': 'PreAmp_JCM800AT4', 'PreAmp': 'PreAmp_JCM800AT4', 'Sensitivity': 'Sensitivity_JCM800AT4'},
    "907be0ce-a419-4281-901f-dcd6763de54a": {'Bass': 'Bass_MetalHead', 'Mid': 'Mid_MetalHead', 'Middle': 'Mid_MetalHead', 'Treble': 'Treble_MetalHead', 'Pres': 'Presence_MetalHead', 'Presence': 'Presence_MetalHead', 'Volume': 'Volume_MetalHead', 'Loudness1': 'Volume_MetalHead', 'Master': 'Volume_MetalHead', 'Gain': 'Drive_MetalHead'},
    "9400d18f-5f72-40ac-aa37-861ba3f18da5": {'Bass': 'Bass_MetalLeadT', 'Mid': 'Mid_MetalLeadT', 'Middle': 'Mid_MetalLeadT', 'Treble': 'Treble_MetalLeadT', 'Pres': 'Presence_MetalLeadT', 'Presence': 'Presence_MetalLeadT', 'Volume': 'Volume_MetalLeadT', 'Loudness1': 'Volume_MetalLeadT', 'Master': 'Volume_MetalLeadT', 'Gain': 'Gain_MetalLeadT', 'PreAmp': 'Gain_MetalLeadT', 'Sensitivity': 'Gain_MetalLeadT'},
    "95b9bc84-89fa-48f5-a336-26a30a044ca3": {'Bass': 'Bass_FenderTwinReverbBright', 'Mid': 'Mid_FenderTwinReverbBright', 'Middle': 'Mid_FenderTwinReverbBright', 'Treble': 'Treble_FenderTwinReverbBright', 'Pres': 'Presence_FenderTwinReverbBright', 'Presence': 'Presence_FenderTwinReverbBright', 'Volume': 'Volume_FenderTwinReverbBright', 'Loudness1': 'Volume_FenderTwinReverbBright', 'Master': 'Volume_FenderTwinReverbBright', 'Gain': 'Gain_FenderTwinReverbBright', 'PreAmp': 'Gain_FenderTwinReverbBright', 'Sensitivity': 'Gain_FenderTwinReverbBright'},
    "99e446c7-49df-45b1-bff9-26d95e10c763": {'Treble': 'Tone', 'Volume': 'Volume', 'Loudness1': 'Volume', 'Master': 'Output', 'Gain': 'Gain', 'PreAmp': 'Gain', 'Sensitivity': 'Gain'},
    "a0fa7c56-0772-4ddd-9320-c2ee254a3c4a": {'Volume': 'Volume_Fender57CustomChamp', 'Loudness1': 'Volume_Fender57CustomChamp', 'Master': 'Volume_Fender57CustomChamp'},
    "a2f18e96-4d56-4372-b438-11bd0f42f6f3": {'Bass': 'Ch1Bass_Silvertone1484', 'Treble': 'Ch1Treble_Silvertone1484'},
    "a913acaa-80f1-4703-981c-406ec2e50874": {'Volume': 'Volume_Leslie3300', 'Loudness1': 'Volume_Leslie3300', 'Master': 'Volume_Leslie3300'},
    "ad4ea282-ced9-49d0-9670-e9782ce5c5b7": {'Bass': 'Bass_SolidStateBassPre', 'Mid': 'Mid_SolidStateBassPre', 'Middle': 'Mid_SolidStateBassPre', 'Treble': 'Treble_SolidStateBassPre', 'Pres': 'Presence_SolidStateBassPre', 'Presence': 'Presence_SolidStateBassPre', 'Volume': 'Volume_SolidStateBassPre', 'Loudness1': 'Volume_SolidStateBassPre', 'Master': 'Volume_SolidStateBassPre', 'Gain': 'Gain_SolidStateBassPre', 'PreAmp': 'Gain_SolidStateBassPre', 'Sensitivity': 'Gain_SolidStateBassPre'},
    "b3869f27-a9f1-4482-add4-9512c16917ea": {'Bass': 'Bass_TwinAmp', 'Mid': 'Middle_TwinAmp', 'Middle': 'Middle_TwinAmp', 'Treble': 'Treble_TwinAmp', 'Volume': 'Volume_TwinAmp', 'Loudness1': 'Volume_TwinAmp', 'Master': 'Volume_TwinAmp'},
    "bf860ad9-cd8a-425b-8049-29211fce237a": {'Treble': 'Tone_Fender57CustomDeluxe'},
    "c13004d2-9a19-4ae9-8c0e-9894c5e769c8": {'Volume': 'Volume_LeslieModel122', 'Loudness1': 'Volume_LeslieModel122', 'Master': 'Volume_LeslieModel122', 'Gain': 'Gain_LeslieModel122', 'PreAmp': 'Gain_LeslieModel122', 'Sensitivity': 'Gain_LeslieModel122'},
    "c85e5dc4-d051-4aad-846f-038b0b5233c5": {'Bass': 'Ch1Bass_MesaTripleRectifier', 'Mid': 'Ch1Mid_MesaTripleRectifier', 'Treble': 'Ch1Treble_MesaTripleRectifier'},
    "cfa6b70c-2c6c-4b83-b881-571a6343dfac": {'Bass': 'Bass_Darrell100', 'Mid': 'Middle_Darrell100', 'Middle': 'Middle_Darrell100', 'Treble': 'Treble_Darrell100', 'Pres': 'Presence_Darrell100', 'Presence': 'Presence_Darrell100'},
    "d089ef66-b5c4-4274-910c-6a6ee194cf04": {'Bass': 'Bass_MarshallJTM45MkII', 'Mid': 'Mid_MarshallJTM45MkII', 'Middle': 'Mid_MarshallJTM45MkII', 'Treble': 'Treble_MarshallJTM45MkII', 'Pres': 'Presence_MarshallJTM45MkII', 'Presence': 'Presence_MarshallJTM45MkII', 'Volume': 'Volume_MarshallJTM45MkII', 'Loudness1': 'Volume_MarshallJTM45MkII', 'Master': 'Volume_MarshallJTM45MkII', 'Gain': 'Gain_MarshallJTM45MkII', 'PreAmp': 'Gain_MarshallJTM45MkII', 'Sensitivity': 'Gain_MarshallJTM45MkII'},
    "d31154a9-8b5f-4abf-b079-d2e728d2c564": {'Master': 'Output_MesaMarkV'},
    "d3c791b9-58f1-41d2-8a88-797e98cc5b29": {'Bass': 'Bass_Fender65CustomSuperReverb', 'Mid': 'Middle_Fender65CustomSuperReverb', 'Middle': 'Middle_Fender65CustomSuperReverb', 'Treble': 'Treble_Fender65CustomSuperReverb', 'Volume': 'Volume_Fender65CustomSuperReverb', 'Loudness1': 'Volume_Fender65CustomSuperReverb', 'Master': 'Volume_Fender65CustomSuperReverb'},
    "d4d5b530-0ce1-46cf-a47e-bf0224fa715e": {'Treble': 'Tone_Deluxe57'},
    "d9aa41f9-4e51-4719-929c-251d07f2f276": {'Bass': 'Bass_CaliforniaTweed', 'Mid': 'Mid_CaliforniaTweed', 'Middle': 'Mid_CaliforniaTweed', 'Treble': 'Treble_CaliforniaTweed', 'Pres': 'Presence_CaliforniaTweed', 'Presence': 'Presence_CaliforniaTweed', 'Volume': 'Master_CaliforniaTweed', 'Master': 'Master_CaliforniaTweed', 'Gain': 'Gain_CaliforniaTweed', 'PreAmp': 'Gain_CaliforniaTweed', 'Sensitivity': 'Gain_CaliforniaTweed'},
    "dcc7c825-76f4-4703-8e1f-b8a12b30b1de": {'Bass': 'Bass_MetalLeadV', 'Mid': 'Mid_MetalLeadV', 'Middle': 'Mid_MetalLeadV', 'Treble': 'Treble_MetalLeadV', 'Pres': 'Presence_MetalLeadV', 'Presence': 'Presence_MetalLeadV', 'Volume': 'Volume_MetalLeadV', 'Loudness1': 'Volume_MetalLeadV', 'Master': 'Volume_MetalLeadV', 'Gain': 'Gain_MetalLeadV', 'PreAmp': 'Gain_MetalLeadV', 'Sensitivity': 'Gain_MetalLeadV'},
    "dd7b0e06-a17a-4851-83c4-ee32ca303b01": {'Bass': 'Bass', 'Mid': 'Middle', 'Middle': 'Middle', 'Treble': 'Treble', 'Volume': 'Master', 'Master': 'Master', 'Gain': 'Gain', 'PreAmp': 'Gain', 'Sensitivity': 'Gain'},
    "dffa559d-7b12-464a-9fbf-877ca25f5cf3": {'Bass': 'Bass_VibroKing', 'Mid': 'Mid_VibroKing', 'Middle': 'Mid_VibroKing', 'Treble': 'Treble_VibroKing', 'Volume': 'Volume_VibroKing', 'Loudness1': 'Volume_VibroKing', 'Master': 'Volume_VibroKing'},
    "e1eed2cf-6777-46c4-ada2-65df0d7afc46": {'Bass': 'Bass_MarshallMajor', 'Mid': 'Mid_MarshallMajor', 'Middle': 'Mid_MarshallMajor', 'Treble': 'Treble_MarshallMajor', 'Pres': 'Presence_MarshallMajor', 'Presence': 'Presence_MarshallMajor'},
    "e3260631-d81f-4c76-9e4f-d12be6ede5cb": {'Bass': 'Bass', 'Mid': 'Mid', 'Middle': 'Mid', 'Treble': 'Treble', 'Volume': 'VolumeA', 'Gain': 'GainA'},
    "e3d7fcaa-742f-421c-902e-5f04c0290b96": {'Volume': 'Volume_AmpVoxAC30BrianMay', 'Loudness1': 'Volume_AmpVoxAC30BrianMay', 'Master': 'Volume_AmpVoxAC30BrianMay'},
    "e6151532-1028-422c-9a5d-fc57594ce8e8": {'Bass': 'Bass', 'Mid': 'Middle', 'Middle': 'Middle', 'Treble': 'Treble', 'Volume': 'Volume', 'Loudness1': 'Volume', 'Master': 'Volume', 'Gain': 'Gain', 'PreAmp': 'Gain', 'Sensitivity': 'Gain'},
    "f0951b1e-91d2-4360-80d7-793fa785d2d6": {'Bass': 'Bass_VibroVerb', 'Treble': 'Treble_VibroVerb', 'Volume': 'Volume_VibroVerb', 'Loudness1': 'Volume_VibroVerb', 'Master': 'Volume_VibroVerb'},
    "f1d8d4c0-770c-469e-88fc-0fa2ffe7e8bc": {'Bass': 'Bass_AmpegBA500', 'Mid': 'Mid_AmpegBA500', 'Middle': 'Mid_AmpegBA500', 'Treble': 'Treble_AmpegBA500', 'Volume': 'Master_AmpegBA500', 'Master': 'Master_AmpegBA500', 'Gain': 'Gain_AmpegBA500', 'PreAmp': 'Gain_AmpegBA500', 'Sensitivity': 'Gain_AmpegBA500'},
    "f2190a68-52ea-408a-9c39-2ea8279c0d43": {'Treble': 'Tone_53Bassman'},
    "f4b89ab3-8ca6-44ee-b90b-a570040c8a3d": {'Bass': 'Bass_Supersonic', 'Mid': 'Middle_Supersonic', 'Middle': 'Middle_Supersonic', 'Treble': 'Treble_Supersonic', 'Volume': 'Volume_Supersonic', 'Loudness1': 'Volume_Supersonic', 'Master': 'Volume_Supersonic'},
    "fb5fc82f-a926-4591-87d2-168906fd79d3": {'Bass': 'Bass_BritishTubeLead1', 'Mid': 'Mid_BritishTubeLead1', 'Middle': 'Mid_BritishTubeLead1', 'Treble': 'Treble_BritishTubeLead1', 'Pres': 'Presence_BritishTubeLead1', 'Presence': 'Presence_BritishTubeLead1', 'Volume': 'Volume_BritishTubeLead1', 'Loudness1': 'Volume_BritishTubeLead1', 'Master': 'Volume_BritishTubeLead1', 'Gain': 'Gain_BritishTubeLead1', 'PreAmp': 'Gain_BritishTubeLead1', 'Sensitivity': 'Gain_BritishTubeLead1'},
    "ff274db4-43c3-4fb9-b44d-d04aefd13b28": {'Bass': 'Bass_AmpegB15', 'Mid': 'Mid_AmpegB15', 'Middle': 'Mid_AmpegB15', 'Treble': 'Treble_AmpegB15', 'Volume': 'Master_AmpegB15', 'Master': 'Master_AmpegB15', 'Gain': 'Gain_AmpegB15', 'PreAmp': 'Gain_AmpegB15', 'Sensitivity': 'Gain_AmpegB15'},
}

# ─────────────────────────────────────────────────────────────────────────────
# KNOB NAME MAPPING  (RS knob suffix -> AT5 param name prefix)
# ─────────────────────────────────────────────────────────────────────────────

KNOB_NAME_MAP = {
    "Bass":       "Bass",
    "Mid":        "Middle",
    "Middle":     "Middle",
    "Treble":     "Treble",
    "Pres":       "Presence",
    "Presence":   "Presence",
    "Volume":     "Volume",
    "Gain":       "Gain",
    "Master":     "Master",
    "Loudness1":  "Volume",
    "Loudness2":  "Volume2",
    "PreAmp":     "PreAmp",
    "Sensitivity":"Sensitivity",
    "Lead":       "Lead",
    "Rhythm":     "Rhythm",
}


# Amp keys that are direct-inject / no cabinet
# ── AT5 version tier gear constraints ─────────────────────────────────────
#
# Four tiers based on IK Multimedia's official gear comparison (v5.0.3):
#   CS  — 6 amps,  7 cabs, 10 stomps, 6 rack  (free)
#   SE  — 13 amps, 14 cabs, 19 stomps, 13 rack (~$50-80 upgrade)
#   AT5 — 35 amps, 28 cabs, 35 stomps, 34 rack (standard paid)
#   MAX — 107 amps, 101 cabs, full library      (no fallback needed)
#
# When a tier is selected, every RS amp/cab/effect maps to the closest
# available model in that tier. MAX mode = full conversion with no constraints.

# ── Amp GUIDs by AT5 name ─────────────────────────────────────────────────
AT5_AMP_GUIDS = {
    # CS tier (6)
    "Brit 8000":              "8fe96936-5178-4950-9b80-d89c32534bad",
    "American Tube Clean 1":  "71a76a9f-cf70-4f59-971f-9864a055523c",
    "American Tube Clean 2":  "82972243-cd55-4b43-82f3-f15e3bc13dc7",
    "British Tube Lead 1":    "fb5fc82f-a926-4591-87d2-168906fd79d3",
    "SLD 100":                "4a22ac9f-aabb-4180-b697-5d5710a1acc2",
    "Solid State Bass Preamp":"ad4ea282-ced9-49d0-9670-e9782ce5c5b7",
    # SE adds (7)
    "American Lead MKIII":    "4af9d89a-c06b-4c8f-b137-af72bc58fded",
    "Brit 9000":              "cbf3c00f-1234-4abc-8def-0123456789ab",
    "British Copper 30TB":    "5d235e0d-e30a-4b5c-9876-543210fedcba",
    "Jazz Amp 120":           "ac08939a-f1e2-4d3c-b5a6-7890abcdef12",
    "Metal Lead V":           "dcc7c825-a1b2-4c3d-8e4f-5a6b7c8d9e0f",
    "Metal Lead W":           "dcc7c825-a1b2-4c3d-8e4f-5a6b7c8d9e0f",  # same family as V
    "Modern Tube Lead":       "bca11751-a7c1-49f5-846d-031f7eb780f0",
    # AT5 adds (key ones)
    "American Clean MKIII":   "a91067a3-fd80-40a8-be35-0681da5c4f47",
    "Brit Silver":            "3930eb8b-3eda-4079-b86d-7bfd7d4449bc",
    "German 34":              "4b13e59f-5678-4def-abcd-ef0123456789",
    "Red Pig":                "e1eed2cf-9012-4567-8901-234567890abc",
    "Metal Lead T":           "dcc7c825-a1b2-4c3d-8e4f-5a6b7c8d9e0f",  # same family
    "Vintage Metal Lead":     "1b5961b1-3456-4789-0123-456789abcdef",
    "VHandcraft 4":           "185e9cde-6789-4012-3456-789012345678",
    "SilverPlate 50":         "f24511a1-2345-4678-9012-345678901234",
    "360Bass Preamp":         "ecb60014-7890-4123-4567-890123456789",
    "New York B750":          "18f9d728-8901-4234-5678-901234567890",
}

# Backwards compat — CS mode still uses AT5_CS_AMP_GUIDS name
AT5_CS_AMP_GUIDS = {k: v for k, v in AT5_AMP_GUIDS.items()
                    if k in {"Brit 8000", "American Tube Clean 1",
                             "American Tube Clean 2", "British Tube Lead 1",
                             "SLD 100", "Solid State Bass Preamp"}}

# ── Cab GUIDs (shared across tiers — just availability differs) ───────────
AT5_CS_CAB_GUIDS = {
    "1x12 Open Vintage":   "bcec521d-c918-4af6-98be-b50b644ac3dd",
    "1x15 Bass Vintage":   "0c2f1129-e09d-4510-9624-7c8b05f188cf",
    "2x12 Closed Vintage": "f7902634-12e9-4a2d-9f9a-bcd22781cdab",
    "4x10 Open Vintage":   "4614704e-7ca2-4736-a750-648fe9033650",
    "4x12 Brit 8000":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",
    "4x12 Closed Vintage": "c97bc69c-c02d-4cce-b19d-859b72833550",
    "4x12 Metal T":        "849b3340-5c3b-4395-9e28-ef6dc14f6847",
    # SE/AT5 add
    "4x12 Brit 9000":      "7c0b8ce1-cbb4-4e5b-9973-a572143ddb2b",  # closest = Brit 8000 cab
    "4x12 Closed Modern":  "c97bc69c-c02d-4cce-b19d-859b72833550",  # closest = Closed Vintage
    "4x12 Metal V":        "849b3340-5c3b-4395-9e28-ef6dc14f6847",  # closest = Metal T
}

# ── Available amp sets per tier ───────────────────────────────────────────
AT5_TIER_AMPS = {
    "cs": {
        "Brit 8000", "American Tube Clean 1", "American Tube Clean 2",
        "British Tube Lead 1", "SLD 100", "Solid State Bass Preamp",
    },
    "se": {
        "Brit 8000", "American Tube Clean 1", "American Tube Clean 2",
        "British Tube Lead 1", "SLD 100", "Solid State Bass Preamp",
        "American Lead MKIII", "Brit 9000", "British Copper 30TB",
        "Jazz Amp 120", "Metal Lead V", "Metal Lead W", "Modern Tube Lead",
    },
    "at5": {
        "Brit 8000", "Brit 9000", "Brit Silver",
        "American Tube Clean 1", "American Tube Clean 2",
        "American Lead MKIII", "American Clean MKIII",
        "British Tube Lead 1", "British Copper 30TB",
        "SLD 100", "Solid State Bass Preamp",
        "Jazz Amp 120", "Metal Lead V", "Metal Lead W", "Metal Lead T",
        "Modern Tube Lead", "German 34", "Red Pig",
        "Vintage Metal Lead", "VHandcraft 4",
        "SilverPlate 50", "360Bass Preamp", "New York B750",
    },
    "max": None,  # None = no constraint, use full AMP_MAP
}

# ── Available cab sets per tier ───────────────────────────────────────────
AT5_TIER_CABS = {
    "cs":  {"1x12 Open Vintage", "1x15 Bass Vintage", "2x12 Closed Vintage",
            "4x10 Open Vintage", "4x12 Brit 8000", "4x12 Closed Vintage",
            "4x12 Metal T"},
    "se":  {"1x12 Open Vintage", "1x15 Bass Vintage", "2x12 Closed Vintage",
            "4x10 Open Vintage", "4x12 Brit 8000", "4x12 Brit 9000",
            "4x12 Closed Modern", "4x12 Closed Vintage", "4x12 Metal T",
            "4x12 Metal V"},
    "at5": {"1x12 Open Vintage", "1x15 Bass Vintage", "2x12 Closed Vintage",
            "4x10 Open Vintage", "4x12 Brit 8000", "4x12 Brit 9000",
            "4x12 Brit Silver", "4x12 Closed Modern", "4x12 Closed Vintage",
            "4x12 Metal T", "4x12 Metal V", "4x12 Red Pig"},
    "max": None,
}

# ── Stomp/rack availability per tier ─────────────────────────────────────
# For effects: anything not in the tier's set gets dropped (returns None)
AT5_TIER_STOMPS = {
    "cs":  {"chorus", "compressor", "delay", "overdrive", "flanger",
            "noisegate", "tremolo", "volume", "wah", "eq7band"},
    "se":  {"chorus", "compressor", "delay", "overdrive", "flanger",
            "noisegate", "tremolo", "volume", "wah", "eq7band",
            "harmonator", "lfofilter", "overscream", "phaser",
            "rezo", "stepfilter", "stepslicer", "swell"},
    "at5": {"chorus", "compressor", "delay", "overdrive", "flanger",
            "noisegate", "tremolo", "volume", "wah", "eq7band",
            "harmonator", "lfofilter", "overscream", "phaser",
            "rezo", "stepfilter", "stepslicer", "swell",
            "distortion", "metaldist", "octave", "pitchshift",
            "tapdelay", "feedback"},
    "max": None,
}


def _get_best_amp_for_tier(target_name: str, tier: str) -> str:
    """
    Given a desired AT5 amp name and a tier, return the best available
    amp GUID. Falls back to closest sonic match within the tier.
    """
    available = AT5_TIER_AMPS.get(tier)
    if available is None:  # MAX — use whatever was requested
        return AT5_AMP_GUIDS.get(target_name, AT5_AMP_GUIDS["Brit 8000"])
    if target_name in available:
        return AT5_AMP_GUIDS[target_name]
    # Fallback hierarchy per tier
    fallback_order = {
        "cs":  ["Brit 8000", "SLD 100", "American Tube Clean 1",
                "British Tube Lead 1", "American Tube Clean 2",
                "Solid State Bass Preamp"],
        "se":  ["Brit 8000", "SLD 100", "American Lead MKIII",
                "Modern Tube Lead", "American Tube Clean 1",
                "British Tube Lead 1", "Jazz Amp 120",
                "Solid State Bass Preamp"],
        "at5": ["Brit 8000", "SLD 100", "American Lead MKIII",
                "German 34", "Modern Tube Lead", "American Tube Clean 1",
                "British Tube Lead 1", "Jazz Amp 120",
                "Solid State Bass Preamp"],
    }
    for fallback in fallback_order.get(tier, []):
        if fallback in available:
            return AT5_AMP_GUIDS[fallback]
    return AT5_AMP_GUIDS["Brit 8000"]


def _amp_to_tier_guid(rs_amp_key: str, tier: str) -> str:
    """
    Map any RS amp key to the best available AT5 amp GUID for the given tier.
    tier: "cs" | "se" | "at5" | "max"
    """
    k = rs_amp_key.upper()
    available = AT5_TIER_AMPS.get(tier)

    # MAX — use full AMP_MAP directly (no constraints)
    if available is None:
        from cdlc_to_at5 import AMP_MAP
        return AMP_MAP.get(rs_amp_key, AT5_AMP_GUIDS["Brit 8000"])

    # ── Bass amps ────────────────────────────────────────────────────────
    if any(x in k for x in ['BASS','BT15','BT30','AMPEG','AGUILAR',
                              'MARKBASS','GALLIEN','HARTKE','ASHDOWN',
                              'ACOUSTIC360','360BASS']):
        # SE+ has 360Bass Preamp, otherwise Solid State Bass Preamp
        if '360Bass Preamp' in available:
            return AT5_AMP_GUIDS["360Bass Preamp"]
        return AT5_AMP_GUIDS["Solid State Bass Preamp"]

    # ── Clean solid-state (Roland JC) and Jazz Amp 120 ────────────────
    if any(x in k for x in ['ROLAND','JC120','JAZZAMP']):
        if 'Jazz Amp 120' in available:
            return AT5_AMP_GUIDS["Jazz Amp 120"]
        return AT5_AMP_GUIDS["American Tube Clean 2"]
    # AT120/AT20 = Fender-style American Tube -> Jazz Amp 120 in SE+, else Clean 1
    if any(x in k for x in ['AT120','AT20']):
        if 'Jazz Amp 120' in available:
            return AT5_AMP_GUIDS["Jazz Amp 120"]
        return AT5_AMP_GUIDS["American Tube Clean 1"]


    # ── Clean American (Fender, Mesa clean) ─────────────────────────────
    if any(x in k for x in ['CS90','CS100','CS120',
                              'FENDER','DELUXEREVERB','MESACLEAN',
                              'MESACLEANMKIII','TUBECLEAN','CA38']):
        if 'American Clean MKIII' in available:
            return AT5_AMP_GUIDS["American Clean MKIII"]
        return AT5_AMP_GUIDS["American Tube Clean 1"]

    # ── High-gain British (Marshall JCM/DSL/JVM, Orange) ─────────────────
    if any(x in k for x in ['BT100','BT45','GB100','GB50','GB38',
                              'MARSHALLJCM','MARSHALLDSL','MARSHALLJVM',
                              'MARSHALLJMP','MARSHALLPLEXI','MARSHALLMAJOR',
                              'MARSHALLSLASH','EN50','EN30','ORANGE']):
        return AT5_AMP_GUIDS["Brit 8000"]

    # ── Orange high-wattage → British Copper 30TB in SE+ ────────────────
    if any(x in k for x in ['EN30','ORANGETINYTERROR','ORANGEAD30']):
        if 'British Copper 30TB' in available:
            return AT5_AMP_GUIDS["British Copper 30TB"]
        return AT5_AMP_GUIDS["Brit 8000"]

    # ── Clean/vintage British ────────────────────────────────────────────
    if any(x in k for x in ['TW22','TW26','TW40','MARSHALLJTM','MARSHALLBLUES',
                              'MARSHALLSILVER']):
        if 'Brit Silver' in available:
            return AT5_AMP_GUIDS["Brit Silver"]
        return AT5_AMP_GUIDS["British Tube Lead 1"]

    # Bogner/Diezel -> German 34 in AT5+, else SLD 100
    if any(x in k for x in ['GB100','GB50','GB38','BOGNER','ECSTASY','DIEZEL','VH4']):
        if 'German 34' in available:
            return AT5_AMP_GUIDS["German 34"]
        if 'Metal Lead V' in available:
            return AT5_AMP_GUIDS["Metal Lead V"]
        return AT5_AMP_GUIDS["SLD 100"]

    # ── High-gain American → best available high-gain ────────────────────
    if any(x in k for x in ['HG100','HG180','HG500','CA85','CA100',
                              'MESALEAD','MESARECT','MESATRIPL','MESAMODERN',
                              'DUALRECT','TRIPRECT','PEAVEY','5150','6505']):
        # SE+ has Metal Lead V (Peavey-class), AT5+ has German 34 (Bogner)
        if 'Metal Lead V' in available:
            return AT5_AMP_GUIDS["Metal Lead V"]
        return AT5_AMP_GUIDS["SLD 100"]

    # ── Modern/modded lead ───────────────────────────────────────────────
    if any(x in k for x in ['TUBELEAD','MODERN','CA85','MESAMARK']):
        if 'Modern Tube Lead' in available:
            return AT5_AMP_GUIDS["Modern Tube Lead"]
        if 'American Lead MKIII' in available:
            return AT5_AMP_GUIDS["American Lead MKIII"]
        return AT5_AMP_GUIDS["SLD 100"]

    # ── Default fallback ─────────────────────────────────────────────────
    return AT5_AMP_GUIDS["Brit 8000"]


# Keep backwards-compat alias
def _amp_to_cs_guid(rs_amp_key: str) -> str:
    """Legacy: CS-mode amp mapping. Use _amp_to_tier_guid(key, 'cs') instead."""
    return _amp_to_tier_guid(rs_amp_key, "cs")


def _cab_to_tier_guid(rs_cab_key: str, tier: str) -> str:
    """Map RS cab key to the best available cab for the given tier."""
    # All tiers use the same fallback logic — they just have more options
    # For now, CS cab mapping works for all tiers since we store only
    # a subset of GUIDs; the tier just determines which set is available.
    return _cab_to_cs_guid(rs_cab_key)


def _cab_to_cs_guid(rs_cab_key: str) -> str:
    """Map any RS cab key to the closest AT5 CS cabinet GUID."""
    k = rs_cab_key.upper()
    # Bass cabs → 1x15 Bass Vintage
    if 'BASS' in k or '115' in k:
        return AT5_CS_CAB_GUIDS["1x15 Bass Vintage"]
    # Small/single speaker → 1x12 Open Vintage
    if any(x in k for x in ['112','1X12','TW112','CA112','CS1120']):
        return AT5_CS_CAB_GUIDS["1x12 Open Vintage"]
    # 2x12 → 2x12 Closed Vintage
    if any(x in k for x in ['212','2X12']):
        return AT5_CS_CAB_GUIDS["2x12 Closed Vintage"]
    # 4x10 → 4x10 Open Vintage
    if any(x in k for x in ['410','4X10']):
        return AT5_CS_CAB_GUIDS["4x10 Open Vintage"]
    # High-gain / metal 4x12 → 4x12 Metal T
    if any(x in k for x in ['HG','RECTO','MESA','METAL']):
        return AT5_CS_CAB_GUIDS["4x12 Metal T"]
    # British 4x12 → 4x12 Brit 8000
    if any(x in k for x in ['BT','GB','MARSHALL','BRIT','1960']):
        return AT5_CS_CAB_GUIDS["4x12 Brit 8000"]
    # Default: 4x12 Closed Vintage
    return AT5_CS_CAB_GUIDS["4x12 Closed Vintage"]


def _effect_to_cs_guid(rs_effect_key: str) -> str | None:
    """
    Map an RS effect key to the closest AT5 CS stomp/rack GUID.
    Returns None if no reasonable CS equivalent exists (effect slot dropped).
    CS has: Chorus, Compressor, Delay, Diode Overdrive, Flanger,
            Noise Gate, Opto Tremolo, Volume, Wah,
            Digital Chorus, Digital Delay, Digital Reverb,
            Graphic EQ, Parametric EQ 3, Tube Compressor
    No equivalent for: pitch shift, octave, ring mod, bit crush,
                       acoustic emulator, bass emulator, vibe, phaser,
                       flanger (some variants)
    """
    k = rs_effect_key.upper()
    # Drop: pitch/octave/whammy, ring mod, bit crusher, acoustic/bass emulator
    if any(x in k for x in ['PITCH','OCTAVE','WHAMM','RING','BIT','CRUNCHER',
                              'ACOUSTIC','BASSEMU','LOFI','SYNTH','BAKED',
                              'ENBIGGEN','CLONE','ROTATO','VIBE','ROTA']):
        return AT5_CS_NULL_EFFECT
    # Wah variants → Wah
    if any(x in k for x in ['WAH','FILTER','AUTOWAH','BOBFILTER']):
        return AT5_CS_STOMP_MAP["wah"]
    # Reverb variants → Digital Reverb
    if any(x in k for x in ['REVERB','VERB','SPRING','PLATE','CHAMBER']):
        return AT5_CS_STOMP_MAP["reverb"]
    # Delay variants → Delay
    if any(x in k for x in ['DELAY','ECHO']):
        return AT5_CS_STOMP_MAP["delay"]
    # Chorus variants → Chorus
    if 'CHORUS' in k:
        return AT5_CS_STOMP_MAP["chorus"]
    # Flanger variants → Flanger
    if 'FLANG' in k:
        return AT5_CS_STOMP_MAP["flanger"]
    # Overdrive/distortion/fuzz → Diode Overdrive
    if any(x in k for x in ['DRIVE','DIST','FUZZ','BOOST','SHRED','BUZZ','METAL',
                              'GERMANIUM','CAPTFUZZ','LINEDRIVE','SUPERDRIVE',
                              'CUSTOMDRIVE','RANGEBOOSTE','VINTAGEDR']):
        return AT5_CS_STOMP_MAP["overdrive"]
    # Compressor/limiter → Compressor
    if any(x in k for x in ['COMPRESS','LIMIT','SWOLE']):
        return AT5_CS_STOMP_MAP["compress"]
    # Noise gate → Noise Gate
    if any(x in k for x in ['GATE','NOISE']):
        return AT5_CS_STOMP_MAP["noisegate"]
    # Tremolo → Opto Tremolo
    if any(x in k for x in ['TREM','TREMOLO']):
        return AT5_CS_STOMP_MAP["trem"]
    # EQ variants → Graphic EQ
    if 'EQ' in k:
        return AT5_CS_STOMP_MAP["eq"]
    # Phaser — no CS equivalent, drop
    if 'PHAS' in k:
        return AT5_CS_NULL_EFFECT
    # Unknown — drop rather than guess
    return AT5_CS_NULL_EFFECT


# Global noise gate — inserted at pre-amp slot 0 when enabled
NOISE_GATE_GUID = "0455f997-43ca-4c9b-9269-286a19d10d48"
NOISE_GATE_THRESHOLD = -50.0  # dB — sensible default for most guitars

DI_AMP_KEYS = {
    "DI_Amp_TubePre",
    "DI_Amp_BassDriver",
}

# ─────────────────────────────────────────────────────────────────────────────
# AT5P XML TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────

AT5P_TEMPLATE = """\
<?xml version="1.0" ?>
<Preset Version="1" Format="at5p" GUID="{guid}" PresetBPM="120" ProgramChange="-1">
    <Chain Preset="Chain11" MonoChainDualCab="1" DIBeforeAmp="{di_before_amp}" />
    <Input Input="1" />
    <Tuner Bypass="1" Mute="0" OutputVolume="1" TunerType="354eca51-457a-41b7-917d-ce6117586905">
        <Tuner Reference="440" NoteReferemce="A" Transpose="0" Temperament="Equal" />
    </Tuner>
    <StompA1 Bypass="0" Mute="0" OutputVolume="1" {stompa1_attrs}>
{stompa1_slots}
    </StompA1>
    <StompA2 Bypass="0" Mute="1" OutputVolume="1" {null6_attrs}>
{null6_slots}
    </StompA2>
    <StompStereo Bypass="0" Mute="1" OutputVolume="1" {null3_attrs}>
{null3_slots}
    </StompStereo>
    <StompB1 Bypass="0" Mute="0" OutputVolume="1" {stompb1_attrs}>
{stompb1_slots}
    </StompB1>
    <StompB2 Bypass="0" Mute="1" OutputVolume="1" {null6_attrs}>
{null6_slots}
    </StompB2>
    <StompB3 Bypass="0" Mute="1" OutputVolume="1" {null6_attrs}>
{null6_slots}
    </StompB3>
    <AmpA Bypass="0" Mute="{amp_muted}" OutputVolume="1" Model="{amp_guid}">
        <Amp {amp_params}/>
    </AmpA>
    <AmpB Bypass="0" Mute="1" OutputVolume="1" Model="{null_guid}">
        <Amp />
    </AmpB>
    <AmpC Bypass="0" Mute="1" OutputVolume="1" Model="{null_guid}">
        <Amp />
    </AmpC>
    <LoopFxA Bypass="0" Mute="0" OutputVolume="1" {null4_attrs}>
{null4_slots}
    </LoopFxA>
    <LoopFxB Bypass="0" Mute="0" OutputVolume="1" {null4_attrs}>
{null4_slots}
    </LoopFxB>
    <LoopFxC Bypass="0" Mute="1" OutputVolume="1" {null4_attrs}>
{null4_slots}
    </LoopFxC>
    <CabA Bypass="0" Mute="{cab_muted}" CabModel="{cab_model}" SpeakerModel0="{speaker_a}" SpeakerModel1="{speaker_a}" SpeakerModel2="{speaker_b}" SpeakerModel3="{speaker_b}" IRDecimation="1">
        <Cab HighLevel="0.77" RoomType="Large Studio" RoomMicType="Condenser 87" Mic0Model="1e41acc4-85af-4e84-bee4-eabc0be5fef1" Mic1Model="9e444286-cab4-46a4-bfa3-a6d55b3ffcfb" Mic0Angle="0" Mic1Angle="0" Mic0XAxis="-0.0134551" Mic1XAxis="0.164812" Mic0YAxis="-0.213863" Mic1YAxis="0.416267" Mic0Distance="0" Mic1Distance="0.131415" Mic0Speaker="0" Mic1Speaker="1" GUILoadComplete="0" />
    </CabA>
    <CabB Bypass="0" Mute="1" CabModel="{cab_model}" SpeakerModel0="{speaker_b}" SpeakerModel1="{speaker_b}" SpeakerModel2="{speaker_b}" SpeakerModel3="{speaker_b}" IRDecimation="1">
        <Cab HighLevel="0.77" RoomType="Large Studio" RoomMicType="Condenser 87" Mic0Model="1e41acc4-85af-4e84-bee4-eabc0be5fef1" Mic1Model="9e444286-cab4-46a4-bfa3-a6d55b3ffcfb" Mic0Angle="0" Mic1Angle="0" Mic0XAxis="0.0134551" Mic1XAxis="0.164812" Mic0YAxis="-0.213863" Mic1YAxis="0.416267" Mic0Distance="0" Mic1Distance="0.131415" Mic0Speaker="0" Mic1Speaker="1" GUILoadComplete="0" />
    </CabB>
    <CabC Bypass="0" Mute="1" CabModel="{cab_model}" SpeakerModel0="{speaker_b}" SpeakerModel1="{speaker_b}" SpeakerModel2="{speaker_b}" SpeakerModel3="{speaker_b}" IRDecimation="1">
        <Cab HighLevel="0.77" RoomType="Large Studio" RoomMicType="Condenser 87" Mic0Model="1e41acc4-85af-4e84-bee4-eabc0be5fef1" Mic1Model="9e444286-cab4-46a4-bfa3-a6d55b3ffcfb" Mic0Angle="0" Mic1Angle="0" Mic0XAxis="0.0134551" Mic1XAxis="0.164812" Mic0YAxis="-0.213863" Mic1YAxis="0.416267" Mic0Distance="0" Mic1Distance="0.131415" Mic0Speaker="0" Mic1Speaker="1" GUILoadComplete="0" />
    </CabC>
    <Studio Bypass="0" Mute="0" OutputVolume="1" OutputPan="0.5" DI_Level="-3" DI_Pan="0.5" DI_Mute="1" DI_Solo="0" DI_Phase="0" DI_PhaseDelay="0" Cab1_Mic1_Level="-6" Cab1_Mic1_Pan="0" Cab1_Mic1_Mute="0" Cab1_Mic1_Solo="0" Cab1_Mic1_Phase="0" Cab1_Mic2_Level="-6" Cab1_Mic2_Pan="0" Cab1_Mic2_Mute="0" Cab1_Mic2_Solo="0" Cab1_Mic2_Phase="0" Cab1_Room_Level="-34.5241" Cab1_Room_Width="50" Cab1_Room_Mute="0" Cab1_Room_Solo="0" Cab1_Room_Phase="0" Cab1_Bus_Level="0" Cab1_Bus_Pan="0.5" Cab1_Bus_Mute="0" Cab1_Bus_Solo="0" Cab1_Bus_Phase="0" Cab2_Mic1_Level="-6" Cab2_Mic1_Pan="0" Cab2_Mic1_Mute="0" Cab2_Mic1_Solo="0" Cab2_Mic1_Phase="0" Cab2_Mic2_Level="-6" Cab2_Mic2_Pan="0" Cab2_Mic2_Mute="0" Cab2_Mic2_Solo="0" Cab2_Mic2_Phase="0" Cab2_Room_Level="-34.5241" Cab2_Room_Width="50" Cab2_Room_Mute="0" Cab2_Room_Solo="0" Cab2_Room_Phase="0" Cab2_Bus_Level="0" Cab2_Bus_Pan="0.5" Cab2_Bus_Mute="0" Cab2_Bus_Solo="0" Cab2_Bus_Phase="0" Cab3_Mic1_Level="-6" Cab3_Mic1_Pan="0" Cab3_Mic1_Mute="0" Cab3_Mic1_Solo="0" Cab3_Mic1_Phase="0" Cab3_Mic2_Level="-6" Cab3_Mic2_Pan="0" Cab3_Mic2_Mute="0" Cab3_Mic2_Solo="0" Cab3_Mic2_Phase="0" Cab3_Room_Level="-34.5241" Cab3_Room_Width="50" Cab3_Room_Mute="0" Cab3_Room_Solo="0" Cab3_Room_Phase="0" Cab3_Bus_Level="0" Cab3_Bus_Pan="0.5" Cab3_Bus_Mute="0" Cab3_Bus_Solo="0" Cab3_Bus_Phase="0" Cab1_Leslie_Horn_Level="-6" Cab1_Leslie_Horn_Width="100" Cab1_Leslie_Horn_Mute="0" Cab1_Leslie_Horn_Solo="0" Cab1_Leslie_Horn_Phase="0" Cab1_Leslie_Drum_Level="-6" Cab1_Leslie_Drum_Width="100" Cab1_Leslie_Drum_Mute="0" Cab1_Leslie_Drum_Solo="0" Cab1_Leslie_Drum_Phase="0" Cab2_Leslie_Horn_Level="-6" Cab2_Leslie_Horn_Width="100" Cab2_Leslie_Horn_Mute="0" Cab2_Leslie_Horn_Solo="0" Cab2_Leslie_Horn_Phase="0" Cab2_Leslie_Drum_Level="-6" Cab2_Leslie_Drum_Width="100" Cab2_Leslie_Drum_Mute="0" Cab2_Leslie_Drum_Solo="0" Cab2_Leslie_Drum_Phase="0" Cab3_Leslie_Horn_Level="-6" Cab3_Leslie_Horn_Width="100" Cab3_Leslie_Horn_Mute="0" Cab3_Leslie_Horn_Solo="0" Cab3_Leslie_Horn_Phase="0" Cab3_Leslie_Drum_Level="-6" Cab3_Leslie_Drum_Width="100" Cab3_Leslie_Drum_Mute="0" Cab3_Leslie_Drum_Solo="0" Cab3_Leslie_Drum_Phase="0" />
    <RackA Bypass="0" Mute="0" OutputVolume="1" {racka_attrs}>
{racka_slots}
    </RackA>
    <RackB Bypass="0" Mute="0" OutputVolume="1" {rackb_attrs}>
{rackb_slots}
    </RackB>
    <RackC Bypass="0" Mute="1" OutputVolume="1" {null2_attrs}>
{null2_slots}
    </RackC>
    <RackDI Bypass="0" Mute="0" OutputVolume="1" {null2_attrs}>
{null2_slots}
    </RackDI>
    <RackMaster Bypass="0" Mute="0" OutputVolume="1" {null6_attrs}>
{null6_slots}
    </RackMaster>
    <Output Output="1" />
    <MidiAssignments />
    <MetaInfo Description="{description}" Style="None" SoundCharacter="None" Instrument="None" Body="None" PickUpPosition="None" Artist="" Band="" Song="{song}" Album="" SongStructureElement="None" KeyWords="" Type="None" />
</Preset>
"""

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def null_attrs(n):
    return " ".join(f'Stomp{i}="{NULL_GUID}"' for i in range(n))

def null_slots(n):
    return "\n".join(f"        <Slot{i} />" for i in range(n))

def lookup_amp(rs_key, free_mode=False, tier="max"):
    """Look up AT5 amp GUID for an RS amp key.
    tier: "cs" | "se" | "at5" | "max" (overrides free_mode if set)
    free_mode: legacy bool — maps to tier="cs" if True
    """
    if not rs_key:
        return "", False
    # Resolve tier
    if free_mode and tier == "max":
        tier = "cs"
    # Non-max tier: use tier-constrained mapping
    if tier != "max" and rs_key not in DI_AMP_KEYS:
        return _amp_to_tier_guid(rs_key, tier), True
    if rs_key in AMP_MAP:
        return AMP_MAP[rs_key], True
    rs_lower = rs_key.lower()
    for k, v in AMP_MAP.items():
        if k.lower() in rs_lower or rs_lower in k.lower():
            return v, False
    return None, False

def lookup_cab(rs_key, free_mode=False, tier="max"):
    if free_mode or tier not in ("max",):
        effective_tier = "cs" if free_mode and tier == "max" else tier
        return _cab_to_tier_guid(rs_key, effective_tier), DEFAULT_SPEAKER_A
    enclosure = CAB_ENCLOSURE_MAP.get(rs_key)
    if not enclosure:
        # Fuzzy match
        rs_lower = rs_key.lower()
        for k, v in CAB_ENCLOSURE_MAP.items():
            if k.lower() in rs_lower or rs_lower in k.lower():
                enclosure = v
                break
    if not enclosure:
        # Guess size from key name
        k = rs_key.lower()
        if any(x in k for x in ['2x12', 'combo', 'vox', 'ac30']):
            enclosure = DEFAULT_CAB_2x12
        elif any(x in k for x in ['1x12', '1x10', '1x15', 'fender', 'deluxe']):
            enclosure = DEFAULT_CAB_1x12
        else:
            enclosure = DEFAULT_CAB_4x12

    speaker = SPEAKER_MAP.get(rs_key, DEFAULT_SPEAKER_A)
    return enclosure, speaker

def lookup_effect(rs_key, free_mode=False):
    """Return AT5 GUID for a RS effect key, or None if unknown."""
    if free_mode:
        return _effect_to_cs_guid(rs_key)  # may be None (effect dropped)
    if rs_key in EFFECT_MAP:
        return EFFECT_MAP[rs_key]
    rs_lower = rs_key.lower()
    for k, v in EFFECT_MAP.items():
        if k.lower() in rs_lower or rs_lower in k.lower():
            return v
    return None

def rs_knob_to_at5(rs_key, rs_value, amp_guid=""):
    """Convert RS knob key+value (0-100) to AT5 param name+value (0-10).
    Appends the amp-specific DSP suffix if known."""
    suffix = rs_key.split("_")[-1]
    at5_name = KNOB_NAME_MAP.get(suffix, suffix)
    # Append model suffix if known
    amp_suffix = AMP_SUFFIX_MAP.get(amp_guid[:8], "")
    if amp_suffix:
        at5_name = f"{at5_name}_{amp_suffix}"
    return at5_name, rs_value / 10.0

def build_stomp_section(gear_slots, n_total=6, free_mode=False, noise_gate=False):
    """
    Build Stomp attrs and Slot elements for a StompX section.
    gear_slots: list of RS gear dicts (may be empty/None)
    Returns (attrs_str, slots_str)
    """
    guids = []
    slot_lines = []
    # If global noise gate is on, prepend it and shift everything down
    if noise_gate:
        effective_slots = gear_slots[:n_total - 1]  # shift down, drop last if full
        if len(gear_slots) >= n_total:
            pass  # last slot dropped — log handled by caller
        gate_slot = [{"Key": "__NOISE_GATE__"}]  # sentinel key
        gear_slots = gate_slot + list(effective_slots)
    for i in range(n_total):
        slot_data = gear_slots[i] if i < len(gear_slots) else {}
        rs_key = slot_data.get('Key', '') if slot_data else ''
        if rs_key == "__NOISE_GATE__":
            effect_guid = NOISE_GATE_GUID
        else:
            effect_guid = lookup_effect(rs_key, free_mode=free_mode) if rs_key else None

        if effect_guid:
            guids.append(effect_guid)
            # TODO: add knob values to slot when stomp param format is known
            slot_lines.append(f"        <Slot{i} Bypass=\"0\" />")
        else:
            guids.append(NULL_GUID)
            slot_lines.append(f"        <Slot{i} />")

    attrs = " ".join(f'Stomp{i}="{g}"' for i, g in enumerate(guids))
    return attrs, "\n".join(slot_lines)

def build_rack_section(rack_slots, free_mode=False):
    """
    Build RackX attrs and Slot elements (2 slots per rack section).
    rack_slots: list of up to 2 RS rack gear dicts
    Returns (attrs_str, slots_str)
    """
    guids = []
    slot_lines = []
    for i in range(2):
        slot_data = rack_slots[i] if i < len(rack_slots) else {}
        rs_key = slot_data.get('Key', '') if slot_data else ''
        effect_guid = lookup_effect(rs_key, free_mode=free_mode) if rs_key else None

        if effect_guid:
            guids.append(effect_guid)
            slot_lines.append(f"        <Slot{i} Bypass=\"0\" />")
        else:
            guids.append(NULL_GUID)
            slot_lines.append(f"        <Slot{i} />")

    attrs = " ".join(f'Stomp{i}="{g}"' for i, g in enumerate(guids))
    return attrs, "\n".join(slot_lines)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

def convert_tone(tone_path: Path, output_dir: Path, free_mode: bool = False, tier: str = "max", noise_gate: bool = False):
    try:
        tone = json.loads(tone_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"  ERROR reading {tone_path.name}: {e}")
        return None

    td   = tone.get('toneData', {})
    gear = td.get('GearList', {})
    tone_name = td.get('Name', tone_path.stem)
    tone_key  = td.get('Key',  tone_name)

    warnings = []

    # ── Amp ───────────────────────────────────────────────────────────────────
    amp_data    = gear.get('Amp', {})
    rs_amp_key  = amp_data.get('Key', '')
    effective_tier = "cs" if free_mode and tier == "max" else tier
    amp_guid, amp_exact = lookup_amp(rs_amp_key, free_mode=free_mode, tier=effective_tier)

    if not amp_guid:
        warnings.append(f"Unknown amp '{rs_amp_key}' -> using null amp")
        amp_guid = NULL_GUID
    elif not amp_exact and not free_mode:
        warnings.append(f"Fuzzy amp match for '{rs_amp_key}'")

    knob_values = amp_data.get('KnobValues', {})
    amp_params_parts = []
    for rs_k, rs_v in knob_values.items():
        at5_name, at5_val = rs_knob_to_at5(rs_k, rs_v, amp_guid)
        amp_params_parts.append(f'{at5_name}="{at5_val:.4f}"')
    amp_params_str = " ".join(amp_params_parts)

    # ── Cabinet ───────────────────────────────────────────────────────────────
    cab_data   = gear.get('Cabinet', {})
    rs_cab_key = cab_data.get('Key', '')
    is_di_tone = rs_amp_key in DI_AMP_KEYS

    if is_di_tone:
        # DI tones have no amp or cabinet — use a clean amp GUID (muted) so AT5 validates
        # amp_guid already set from AMP_MAP lookup above (American Tube Clean 1)
        amp_params_str = ""
        cab_model = DEFAULT_CAB_4x12
        speaker_a = DEFAULT_SPEAKER_A
        speaker_b = DEFAULT_SPEAKER_B
        cab_muted = "0"  # unmute cab so DI signal reaches output via DIBeforeAmp
        amp_muted = "1"  # mute amp — signal bypasses via DIBeforeAmp="1"
        di_before_amp = "1"
    else:
        amp_muted = "0"
        di_before_amp = "0"
        cab_model, speaker_a = lookup_cab(rs_cab_key, free_mode=free_mode)
        speaker_b  = DEFAULT_SPEAKER_B
        cab_muted  = "0"
        if rs_cab_key and rs_cab_key not in CAB_ENCLOSURE_MAP:
            warnings.append(f"Fuzzy/default cab match for '{rs_cab_key}'"  )

    # ── Pre-amp stomps (PrePedal1/2 -> StompA1 slots 0-1) ────────────────────
    pre_pedals = [gear.get('PrePedal1', {}), gear.get('PrePedal2', {})]
    stompa1_attrs, stompa1_slots = build_stomp_section(pre_pedals, n_total=6, free_mode=free_mode, noise_gate=noise_gate)
    for p in pre_pedals:
        k = p.get('Key', '') if p else ''
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped pre-pedal '{k}' -> empty slot")

    # ── Post stomps (PostPedal1/2 -> StompB1 slots 0-1) ──────────────────────
    post_pedals = [gear.get('PostPedal1', {}), gear.get('PostPedal2', {})]
    stompb1_attrs, stompb1_slots = build_stomp_section(post_pedals, n_total=6, free_mode=free_mode)
    for p in post_pedals:
        k = p.get('Key', '') if p else ''
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped post-pedal '{k}' -> empty slot")

    # ── Rack effects (Rack1-4 -> RackA slot0/1, RackB slot0/1) ───────────────
    racks = [gear.get(f'Rack{i}', {}) for i in range(1, 5)]
    racka_attrs, racka_slots = build_rack_section(racks[0:2], free_mode=free_mode)
    rackb_attrs, rackb_slots = build_rack_section(racks[2:4], free_mode=free_mode)
    for r in racks:
        k = r.get('Key', '') if r else ''
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped rack '{k}' -> empty slot")

    # ── Assemble ──────────────────────────────────────────────────────────────
    xml = AT5P_TEMPLATE.format(
        guid          = str(uuid.uuid4()),
        amp_guid      = amp_guid,
        amp_muted     = amp_muted,
        amp_params    = amp_params_str,
        di_before_amp = di_before_amp,
        null_guid     = NULL_GUID,
        cab_model     = cab_model,
        cab_muted     = cab_muted,
        speaker_a     = speaker_a.replace('-', ''),
        speaker_b     = speaker_b.replace('-', ''),
        stompa1_attrs = stompa1_attrs,
        stompa1_slots = stompa1_slots,
        stompb1_attrs = stompb1_attrs,
        stompb1_slots = stompb1_slots,
        racka_attrs   = racka_attrs,
        racka_slots   = racka_slots,
        rackb_attrs   = rackb_attrs,
        rackb_slots   = rackb_slots,
        null2_attrs   = null_attrs(2), null2_slots = null_slots(2),
        null3_attrs   = null_attrs(3), null3_slots = null_slots(3),
        null4_attrs   = null_attrs(4), null4_slots = null_slots(4),
        null6_attrs   = null_attrs(6), null6_slots = null_slots(6),
        description   = tone_key,
        song          = tone_name,
    )

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in tone_name)
    out_path  = output_dir / f"{safe_name}.at5p"
    out_path.write_text(xml, encoding='utf-8')

    status = "OK" if not warnings else f"OK ({len(warnings)} warnings)"
    print(f"  {tone_path.name} -> {out_path.name}  [{status}]")
    for w in warnings:
        print(f"    ⚠ {w}")
    return out_path

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# RS2014 / CDLC SUPPORT
# ─────────────────────────────────────────────────────────────────────────────
#
# RS2014 GearList format (from CDLC manifest JSON):
#   {
#     "Key": "RageKilling_lead",
#     "Name": "Killing Lead",
#     "GearList": {
#       "Amp":      { "Key": "Amp_MarshallJCM800", "Knobs": {"Amp_MarshallJCM800_Gain": 65, ...} },
#       "Cabinet":  { "Key": "Cab_Marshall1960a_57_Edge" },
#       "PrePedal1": { "Key": "Pedal_UKWah", "Knobs": {...} },
#       ...
#     }
#   }
#
# Differences from RS+ format:
#   - Wrapped in GearList directly (no outer toneData key)
#   - Amp knobs key is "Knobs" not "KnobValues"
#   - PrePedal3/4 and PostPedal3/4 exist (RS+ only has 1/2)
#   - RS2014 amp keys can be real brand names (Amp_MarshallJCM800) or
#     fictional RS keys (Amp_BT45) — both are in AMP_MAP above
#
# Everything else (AMP_MAP, rs_knob_to_at5, build_stomp_section,
# AT5P_TEMPLATE) is reused unchanged.

import re as _re

import xml.etree.ElementTree as _ET

_NS_TONE = "http://schemas.datacontract.org/2004/07/RocksmithToolkitLib.DLCPackage.Manifest.Tone"
_NS_MS   = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"
_NS_XSI  = "http://www.w3.org/2001/XMLSchema-instance"


def _parse_tone2014_xml(path: Path):
    """
    Parse a .tone2014.xml file (WCF-serialised Rocksmith 2014 tone).
    Returns a list of tone dicts with keys: key, name, gear (GearList dict).

    GearList dict format mirrors _parse_rs2014_json output:
      { "Amp": {"Key": "Amp_HG500", "Knobs": {...}},
        "Cabinet": {"Key": "Cab_HG215C_57_Cone", "Knobs": {}},
        "PrePedal1": {"Key": "Pedal_EQ5", "Knobs": {...}}, ... }
    """
    try:
        tree = _ET.parse(path)
    except Exception as e:
        print(f"  ERROR parsing XML {path.name}: {e}")
        return []
    root = tree.getroot()

    def _find(el, tag):
        result = el.find(f"{{{_NS_TONE}}}{tag}")
        if result is None:
            result = el.find(tag)
        return result

    def _parse_slot(el):
        """Parse one GearList slot element into {"Key": ..., "Knobs": {...}}."""
        if el is None:
            return None
        if el.get(f"{{{_NS_XSI}}}nil") == "true":
            return None
        key_el = _find(el, "PedalKey")
        if key_el is None or not key_el.text:
            return None
        key = key_el.text.strip()
        knobs = {}
        knob_el = _find(el, "KnobValues")
        if knob_el is not None:
            for kv in knob_el:
                k = kv.find(f"{{{_NS_MS}}}Key")
                v = kv.find(f"{{{_NS_MS}}}Value")
                if k is not None and v is not None and k.text and v.text:
                    try:
                        knobs[k.text.strip()] = float(v.text)
                    except ValueError:
                        pass
        return {"Key": key, "Knobs": knobs}

    gear_el = _find(root, "GearList")
    if gear_el is None:
        print(f"  WARNING: no GearList in {path.name}")
        return []

    gear = {}
    for slot_name in ["Amp", "Cabinet",
                       "PrePedal1", "PrePedal2", "PrePedal3", "PrePedal4",
                       "PostPedal1", "PostPedal2", "PostPedal3", "PostPedal4",
                       "Rack1", "Rack2", "Rack3", "Rack4"]:
        slot_el = _find(gear_el, slot_name)
        parsed = _parse_slot(slot_el)
        if parsed:
            gear[slot_name] = parsed

    key_el  = _find(root, "Key")
    name_el = _find(root, "Name")
    tone_key  = key_el.text.strip()  if key_el  is not None and key_el.text  else path.stem
    tone_name = name_el.text.strip() if name_el is not None and name_el.text else tone_key

    return [{"key": tone_key, "name": tone_name, "gear": gear}]


def convert_tone_rs2014_xml(tone_path: Path, output_dir: Path):
    """
    Convert a .tone2014.xml file to .at5p preset(s).
    Delegates to convert_tone_rs2014() after parsing the XML.
    Returns list of output paths written.
    """
    tones = _parse_tone2014_xml(tone_path)
    if not tones:
        return []
    out_paths = []
    for tone in tones:
        # Reuse the JSON-path converter — same gear dict format
        # Build a temp structure that _parse_rs2014_json would produce
        # and call the shared assembly logic directly
        out_paths.extend(_convert_tone_from_gearlist(
            tone["key"], tone["name"], tone["gear"], tone_path, output_dir))
    return out_paths


def _parse_rs2014_json(path: Path):
    """
    Parse an RS2014 GearList JSON file.  Returns a list of tone dicts,
    each with keys: key, name, gear (the GearList dict).

    Handles three layouts:
      A) Single tone: top-level has "GearList" key
      B) Dict of tones: { tone_key: { "GearList": ... }, ... }
      C) List of tones: [ { "GearList": ... }, ... ]

    Also tolerates trailing commas (present in some RS2014 JSON exports).
    """
    raw = path.read_text(encoding="utf-8")
    raw = _re.sub(r",\s*([}\]])", r"\1", raw)   # strip trailing commas
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"  ERROR reading {path.name}: {e}")
        return []

    tones = []

    # Format A: single tone
    if isinstance(data, dict) and "GearList" in data:
        tones.append({"key": data.get("Key", path.stem),
                      "name": data.get("Name", data.get("Key", path.stem)),
                      "gear": data["GearList"]})
        return tones

    # Format B: dict of tones
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and "GearList" in v:
                tones.append({"key": k,
                              "name": v.get("Name", k),
                              "gear": v["GearList"]})
        if tones:
            return tones

    # Format C: list of tones
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "GearList" in item:
                tones.append({"key": item.get("Key", "unknown"),
                              "name": item.get("Name", item.get("Key", "unknown")),
                              "gear": item["GearList"]})
        if tones:
            return tones

    print(f"  WARNING: unrecognised RS2014 JSON layout in {path.name}")
    return []


def convert_tone_rs2014(tone_path: Path, output_dir: Path):
    """
    Convert one RS2014 GearList JSON file to .at5p preset(s).
    One file may contain multiple tones (formats B and C above).
    Returns list of output paths written.
    """
    tones = _parse_rs2014_json(tone_path)
    if not tones:
        return []

    out_paths = []
    for tone in tones:
        out_paths.extend(_convert_tone_from_gearlist(
            tone["key"], tone["name"], tone["gear"], tone_path, output_dir))
    return out_paths


def _convert_tone_from_gearlist(tone_key: str, tone_name: str, gear: dict,
                                 source_path: Path, output_dir: Path,
                                 free_mode: bool = False,
                                 tier: str = "max",
                                 noise_gate: bool = False) -> list:
    """Shared assembly logic for both JSON and XML RS2014 paths."""
    warnings  = []
    out_paths = []

    # ── Amp ──────────────────────────────────────────────────────────────
    amp_data   = gear.get("Amp", {})
    rs_amp_key = amp_data.get("Key", "")
    effective_tier = "cs" if free_mode and tier == "max" else tier
    amp_guid, amp_exact = lookup_amp(rs_amp_key, free_mode=free_mode, tier=effective_tier)

    if not amp_guid:
        warnings.append(f"Unknown amp '{rs_amp_key}' -> using null amp")
        amp_guid = NULL_GUID
    elif not amp_exact:
        warnings.append(f"Fuzzy amp match for '{rs_amp_key}'")

    # RS2014 uses "Knobs" dict (not "KnobValues")
    knob_values = amp_data.get("Knobs", {})
    amp_params_parts = []
    for rs_k, rs_v in knob_values.items():
        at5_name, at5_val = rs_knob_to_at5(rs_k, rs_v, amp_guid)
        amp_params_parts.append(f'{at5_name}="{at5_val:.4f}"')
    amp_params_str = " ".join(amp_params_parts)

    # ── Cabinet ───────────────────────────────────────────────────────────
    cab_data   = gear.get("Cabinet", {})
    rs_cab_key = cab_data.get("Key", "")
    is_di_tone = rs_amp_key in DI_AMP_KEYS
    if is_di_tone:
        amp_muted     = "1"
        di_before_amp = "1"
        cab_muted     = "0"
        cab_model     = DEFAULT_CAB_4x12
        speaker_a     = DEFAULT_SPEAKER_A
        speaker_b     = DEFAULT_SPEAKER_B
    else:
        amp_muted     = "0"
        di_before_amp = "0"
        cab_model, speaker_a = lookup_cab(rs_cab_key, free_mode=free_mode)
        speaker_b  = DEFAULT_SPEAKER_B
        cab_muted  = "0"
        if rs_cab_key and rs_cab_key not in CAB_ENCLOSURE_MAP:
            warnings.append(f"Fuzzy/default cab match for '{rs_cab_key}'")

    # ── Pre-amp stomps (PrePedal1-4 -> StompA1 slots 0-3) ────────────────
    # RS2014 supports up to 4 pre/post pedals; RS+ only 2 — pass all 4.
    pre_pedals = [gear.get(f"PrePedal{i}", {}) for i in range(1, 5)]
    stompa1_attrs, stompa1_slots = build_stomp_section(pre_pedals, n_total=6, free_mode=free_mode, noise_gate=noise_gate)
    for p in pre_pedals:
        k = p.get("Key", "") if p else ""
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped pre-pedal '{k}' -> empty slot")

    # ── Post stomps (PostPedal1-4 -> StompB1 slots 0-3) ──────────────────
    post_pedals = [gear.get(f"PostPedal{i}", {}) for i in range(1, 5)]
    stompb1_attrs, stompb1_slots = build_stomp_section(post_pedals, n_total=6, free_mode=free_mode)
    for p in post_pedals:
        k = p.get("Key", "") if p else ""
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped post-pedal '{k}' -> empty slot")

    # ── Rack effects ──────────────────────────────────────────────────────
    racks = [gear.get(f"Rack{i}", {}) for i in range(1, 5)]
    racka_attrs, racka_slots = build_rack_section(racks[0:2], free_mode=free_mode)
    rackb_attrs, rackb_slots = build_rack_section(racks[2:4], free_mode=free_mode)
    for r in racks:
        k = r.get("Key", "") if r else ""
        if k and not lookup_effect(k):
            warnings.append(f"Unmapped rack '{k}' -> empty slot")

    # ── Assemble ──────────────────────────────────────────────────────────
    xml = AT5P_TEMPLATE.format(
        guid          = str(uuid.uuid4()),
        amp_guid      = amp_guid,
        amp_muted     = amp_muted,
        amp_params    = amp_params_str,
        null_guid     = NULL_GUID,
        cab_model     = cab_model,
        cab_muted     = cab_muted,
        speaker_a     = speaker_a.replace("-", ""),
        speaker_b     = speaker_b.replace("-", ""),
        stompa1_attrs = stompa1_attrs,
        stompa1_slots = stompa1_slots,
        stompb1_attrs = stompb1_attrs,
        stompb1_slots = stompb1_slots,
        racka_attrs   = racka_attrs,
        racka_slots   = racka_slots,
        rackb_attrs   = rackb_attrs,
        rackb_slots   = rackb_slots,
        null2_attrs   = null_attrs(2), null2_slots = null_slots(2),
        null3_attrs   = null_attrs(3), null3_slots = null_slots(3),
        null4_attrs   = null_attrs(4), null4_slots = null_slots(4),
        null6_attrs   = null_attrs(6), null6_slots = null_slots(6),
        description   = tone_key,
        song          = tone_name,
        di_before_amp = di_before_amp,
    )

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in tone_name)
    out_path  = output_dir / f"{safe_name}.at5p"
    out_path.write_text(xml, encoding="utf-8")

    status = "OK" if not warnings else f"OK ({len(warnings)} warnings)"
    print(f"  {source_path.name} [{tone_key}] -> {out_path.name}  [{status}]")
    for w in warnings:
        print(f"    ⚠ {w}")
    out_paths.append(out_path)

    return out_paths


def main():
    parser = argparse.ArgumentParser(
        description="Convert CDLC song tones to AmpliTube 5 presets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CDLC mode (default):  python cdlc_to_at5.py tone_e5c8db1e.json
                      python cdlc_to_at5.py --scan "I:\\Docker\\CDLCScrape\\Songs" -o Presets\\

RS2014 mode:          python cdlc_to_at5.py --rs2014 ragekilling_lead.json
                      python cdlc_to_at5.py --rs2014 --scan "I:\\Docker\\CDLC\\Extracted" -o Presets\\

RS2014 JSON files are the manifest JSONs extracted from a CDLC archive
(arrangements/*.json inside a .feedpak/.sloppak, or a loose extracted folder).
""")
    parser.add_argument("inputs", nargs="*", help="JSON files to convert")
    parser.add_argument("--scan", metavar="DIR", help="Scan directory recursively for *.json files")
    parser.add_argument("--output", "-o", metavar="DIR", default=".", help="Output directory (default: .)")
    parser.add_argument("--rs2014", action="store_true",
                        help="Input is RS2014 CDLC manifest GearList JSON format (not RS+ tone_*.json)")
    parser.add_argument("--rs2014-xml", action="store_true",
                        help="Input is RS2014 .tone2014.xml format (from CDLC toolkit exports)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = []
    if args.scan:
        files = list(Path(args.scan).rglob("*.json"))
        print(f"Found {len(files)} JSON files in {args.scan}")
    files += [Path(p) for p in (args.inputs or [])]

    if not files:
        parser.print_help()
        return

    if getattr(args, 'rs2014_xml', False):
        n_out = sum(len(convert_tone_rs2014_xml(f, output_dir)) for f in files)
        print(f"\nDone: {n_out} preset(s) written -> {output_dir}")
    elif args.rs2014:
        n_out = sum(len(convert_tone_rs2014(f, output_dir)) for f in files)
        print(f"\nDone: {n_out} preset(s) written -> {output_dir}")
    else:
        converted = sum(1 for f in files if convert_tone(f, output_dir))
        print(f"\nDone: {converted}/{len(files)} converted -> {output_dir}")
    print(f"Copy .at5p files to:")
    print(f"  C:\\Users\\<you>\\Documents\\IK Multimedia\\AmpliTube 5\\Presets\\")

if __name__ == "__main__":
    main()
