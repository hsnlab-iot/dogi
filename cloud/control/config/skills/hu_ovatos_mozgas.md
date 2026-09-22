---
id: hu_ovatos_mozgas
name: Óvatos mozgás képesség
description: "Biztonságos pontrol-pontra mozgás és akadályelkerülés lépésenkénti ellenőrzéssel."
required_mcp_tools: [body_attitude, body_move, vision_prompt]
optional_mcp_tools: [todos]
tags: [navigacio, biztonsag, mozgas, akadalyelkerules]
---

# Óvatos navigáció és akadályelkerülés Skill

## Cél
Konzervatív mozgási protokoll a robot biztonságos közlekedéséhez. Minden előrelépés előtt kötelező a közeli terület vizuális ellenőrzése.

## Szabályok
1. Soha ne lépjen hátra (`direction="backward"` tilos).
2. Soha ne menjen előre vakon: minden előrelépés előtt kötelező a lefelé irányzott ellenőrzés.
3. Lépésenkénti haladás: egyszerre legfeljebb 10-15 lépés, utána újraértékelés.
4. Biztonsági távolság: legalább 0.5 m távolság az akadályoktól.

## Végrehajtási protokoll

### 1. Kezdő testtartás
- Hívd meg a `body_attitude` eszközt (`action="tilt"`, `direction="down"`, `amount=15`).

### 2. Közeli útvonal ellenőrzése
- Hívd meg a `vision_prompt` eszközt (`answer_length="short"`) ezzel a kéréssel:
  > "ÚTVONAL ELLENŐRZÉS: A robot előtt lévő talaj (1 méteren belül) teljesen akadálymentes? Válasz: CLEAR vagy BLOCKED. BLOCKED esetén rövid indoklás."

### 3. Döntés és akció
- **Ha PATH == CLEAR:**
  1. Hívd meg a `body_move` eszközt (`action="step"`, `direction="forward"`, `steps=10`).
  2. Tartsd meg vagy állítsd vissza a lefelé döntött testtartást (`body_attitude`, `action="tilt"`, `direction="down"`, `amount=15`).
  3. Ismételd a 2. lépést.

- **Ha PATH == BLOCKED:**
  1. Ne lépj előre.
  2. Kereső fordulás: `body_move` (`action="turn"`, `direction="right"`, `steps=20`).
  3. Ismételd a 2. lépést.

### 4. Lezárás
- Cél elérése vagy megszakítás után állítsd vissza a testtartást:
  - `body_attitude` (`action="reset_attitude"`)
- Jelentsd az állapotot a felhasználónak.

## Vészhelyzet és helyreállítás
- **3 egymás utáni blokkolt fordulás esetén:**
  - Állítsd le a mozgást.
  - `body_attitude` (`action="reset_attitude"`)
  - Jelezd a beragadást, és kérj segítséget Gábortól/operátortól.
- **Eszközhiba esetén:**
  - Azonnal állítsd le a mozgásparancsokat.
  - Próbáld újra egyszer a vizuális ellenőrzést.
  - Tartós hiba esetén jelents hardver/telemetria hibát.