---
id: ovatos_mozgas
name: Óvatos Mozgás Skill
description: "Biztonságos pontrol-pontra mozgás és akadályelkerülés lépésenkénti ellenőrzéssel."
required_mcp_tools: [body_attitude, body_move, vision_prompt]
optional_mcp_tools: [todos]
tags: [navigacio, biztonsag, mozgas, akadalyelkerules]
---

# Ovatos Navigacio es Akadalyelkerules Skill

## Cel
Konzervativ mozgasi protokoll a robot biztonsagos kozlekedesehez. Minden elorelepes elott kotelezo a kozeli terulet vizualis ellenorzese.

## Szabalyok
1. Soha ne lepjen hatra (`direction="backward"` tilos).
2. Soha ne menjen elore vakon: minden elorelepes elott kotelezo a lefel iranyzott ellenorzes.
3. Lepesenkenti haladas: egyszerre legfeljebb 10-15 lepes, utana ujraertekeles.
4. Biztonsagi tavolsag: legalabb 0.5 m tavolsag az akadalyoktol.

## Vegrehajtasi protokoll

### 1. Kezdo testtartas
- Hivd meg a `body_attitude` eszkozt (`action="tilt"`, `direction="down"`, `amount=15`).

### 2. Kozeli utvonal ellenorzese
- Hivd meg a `vision_prompt` eszkozt (`answer_length="short"`) ezzel a keressel:
  > "UTVONAL ELLENORZES: A robot elott levo talaj (1 meteren belul) teljesen akadalymentes? Valasz: CLEAR vagy BLOCKED. BLOCKED eseten rovid indoklas."

### 3. Dontes es akcio
- **Ha PATH == CLEAR:**
  1. Hivd meg a `body_move` eszkozt (`action="step"`, `direction="forward"`, `steps=10`).
  2. Tartsd meg vagy allitsd vissza a lefel döntott testtartast (`body_attitude`, `action="tilt"`, `direction="down"`, `amount=15`).
  3. Ismeteld a 2. lepest.

- **Ha PATH == BLOCKED:**
  1. Ne lepj elore.
  2. Kereso fordulas: `body_move` (`action="turn"`, `direction="right"`, `steps=20`).
  3. Ismeteld a 2. lepest.

### 4. Lezaras
- Cel elerese vagy megszakitas utan allitsd vissza a testtartast:
  - `body_attitude` (`action="reset_attitude"`)
- Jelentsd az allapotot a felhasznalonak.

## Veszhelyzet es helyreallitas
- **3 egymas utani blokkolt fordulas eseten:**
  - Allitsd le a mozgast.
  - `body_attitude` (`action="reset_attitude"`)
  - Jelezd a beragadast, es kerj segitseget Gabortol/operatortol.
- **Eszkozhiba eseten:**
  - Azonnal allitsd le a mozgasparancsokat.
  - Probald ujra egyszer a vizualis ellenorzest.
  - Tartos hiba eseten jelents hardver/telemetria hibat.
