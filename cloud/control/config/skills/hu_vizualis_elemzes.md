---
id: hu_visualis_elemzes
name: VLM Vizuális elemzés képesség
description: "Közvetlen környezeti ellenőrzés és vizuális lekérdezések értékelése VLM (Vision-Language Model) értelmezés segítségével."
required_mcp_tools:
  - vision_prompt
tags: [kép, elemzés]
---

# VLM Vizuális elemzési képesség (Skill)

## Cél
Akkor használandó, amikor a felhasználó vizuális kérdést tesz fel a közvetlen környezetről (pl. "Mit látsz?", "Itt van az X?"), és automatizált vizuális feldolgozásra van szükség.

## Végrehajtási szabályok
1. **Frissességi előírás:** Jelen idejű vizuális lekérdezésre soha ne válaszolj korábbi, múltbeli naplók alapján! Mindig hívd meg a `vision_prompt` eszközt egy friss vizuális megfigyelés rögzítéséhez.
2. **Prompt felépítése:** Fogalmazz meg egy egyértelmű, tömör utasítást a `vision_prompt` eszköz számára, amely pontosan illeszkedik a felhasználó kifejezett szándékához.
   - Példa: A *"Látsz egy piros labdát?"* kérdésre add át a következőt: `"Látható piros labda a képkockán? Válaszolj az objektum nevével és helyével."`
3. **Megfigyelési telemetria:** A `vision_prompt` válaszát kezeld aktív, közvetlen érzékszervi észlelésként. Az eredményt pontosan jelentsd a felhasználónak.