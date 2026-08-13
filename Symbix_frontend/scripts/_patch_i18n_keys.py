# -*- coding: utf-8 -*-
from pathlib import Path

zh_path = Path(r"f:/Symbix/Symbix_frontend/src/i18n/locales/zh-CN.ts")
en_path = Path(r"f:/Symbix/Symbix_frontend/src/i18n/locales/en.ts")

zh = zh_path.read_text(encoding="utf-8")
en = en_path.read_text(encoding="utf-8")

old_home_zh = """    skinSwitched: '已换装「{name}」',
    skinSwitchFailed: '换装失败,请检查皮肤文件',
  },"""
new_home_zh = """    skinSwitched: '已换装「{name}」',
    skinSwitchFailed: '换装失败,请检查皮肤文件',
    windowChat: 'Symbix - 对话',
    windowSkin: 'Symbix - 换肤',
    windowSetting: 'Symbix - 设置',
  },"""

old_skin_zh = """    removeBtn: '删除皮肤',
  },"""
new_skin_zh = """    removeBtn: '删除皮肤',
    empty: '暂无皮肤',
    namePlaceholder: '例如 my-pet',
    pickFolderTitle: '选择 Codex 桌宠文件夹（含 pet.json）',
    skillMessage: '请使用 pet-forge 技能为我生成一个新的桌宠皮肤。\\n\\n皮肤名称：{name}\\n外观描述：{prompt}\\n\\n请严格按照 pet-forge skill 的流水线流程：generate_rig → validate_rig → generate_states_batch → derive_mirrors → validate_states → pack_theme。',
  },"""

if "windowChat:" not in zh:
    if old_home_zh not in zh:
        raise SystemExit("zh home block not found")
    zh = zh.replace(old_home_zh, new_home_zh, 1)

if "empty:" not in zh.split("skinWindow:")[1].split("setting:")[0]:
    if old_skin_zh not in zh:
        raise SystemExit("zh skin block not found")
    zh = zh.replace(old_skin_zh, new_skin_zh, 1)

zh_path.write_text(zh, encoding="utf-8")

old_home_en = """    skinSwitched: 'Skin switched to \"{name}\"',
    skinSwitchFailed: 'Skin switch failed, please check the skin files',
  },"""
new_home_en = """    skinSwitched: 'Skin switched to \"{name}\"',
    skinSwitchFailed: 'Skin switch failed, please check the skin files',
    windowChat: 'Symbix - Chat',
    windowSkin: 'Symbix - Skins',
    windowSetting: 'Symbix - Settings',
  },"""

old_skin_en = """    removeBtn: 'Delete skin',
  },"""
new_skin_en = """    removeBtn: 'Delete skin',
    empty: 'No skins yet',
    namePlaceholder: 'e.g. my-pet',
    pickFolderTitle: 'Select Codex pet folder (with pet.json)',
    skillMessage: 'Please use the pet-forge skill to generate a new pet skin for me.\\n\\nSkin name: {name}\\nAppearance: {prompt}\\n\\nFollow the pet-forge skill pipeline strictly: generate_rig → validate_rig → generate_states_batch → derive_mirrors → validate_states → pack_theme.',
  },"""

if "windowChat:" not in en:
    if old_home_en not in en:
        raise SystemExit("en home block not found")
    en = en.replace(old_home_en, new_home_en, 1)

if "empty:" not in en.split("skinWindow:")[1].split("setting:")[0]:
    if old_skin_en not in en:
        raise SystemExit("en skin block not found")
    en = en.replace(old_skin_en, new_skin_en, 1)

en_path.write_text(en, encoding="utf-8")
print("i18n keys updated OK")
