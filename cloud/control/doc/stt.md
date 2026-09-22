# STT (Speech-to-Text) Koncepció és Megvalósítás

## 1. Koncepció és Célkitűzés

Egy valós idejű, böngészőből működő, adóvevő-szerű (Push-To-Talk) beszéd-szöveg átalakító (STT) rendszer a prompt egyszerű beviteléhez. 

### Főbb elvárások:
* **Floor Control / PTT:** Egyszerre csak egy aktív beszélő lehet. A többi felhasználó addig várakozik, amíg a moderátor másnak nem adja át a szót.
* **Valós idejű üzenetkézbesítés:** A felismerött szöveg azonnal elküldésre kerül prompt számára.
* **Mobilbarát kialakítás:** Touch-alapú Push-To-Talk felület, haptikus visszajelzés (rezgés), valamint a képernyő ébrentartása használat közben.
* **Szerverfüggetlen kliensoldali felismerés:** A beszédfelismerést maga a böngésző végzi, így nincs szükség drága backend STT infrastruktúrára. Andoid és iPhone támogatás, bár az iPhone valószínűleg korlátozott.

---

## 2. Rendszerarchitektúra és Megvalósítás

A rendszer 4 fő komponensből áll:

```
┌────────────────────────┐                   ┌────────────────────────┐
│  Beszélő Kliens        │                   │  Moderátor / Vezérlő   │
│  (user.html)           │                   │  (master.html)         │
└───────────┬────────────┘                   └───────────┬────────────┘
            │                                            │
            │           ┌───────────────────┐            │
            └──────────►│   Ably Realtime   │◄───────────┘
                        │    Pub/Sub Broker │
                        └─────────┬─────────┘
                                  │
                                  ▼
                        ┌───────────────────┐
                        │ Prompt Feldolgozó │
                        │ (prompt.py)       │
                        └───────────────────┘
```

### 2.1. A Rendszer Komponensei
1. **Beszélő Kliens (`user.html`):** A PWA felület, ahol a felhasználók csatlakoznak, és a Push-To-Talk (TALK) gomb nyomvatartásával beszédet rögzítenek.
2. **Moderátor Vezérlő (`master.html`):** A moderátori felület, ahonnan a szoba gazdája kiosztja a beszédjogot (`active-floor`), vagy elnémíthat mindenkit.
3. **Kommunikációs Központ (`Ably Realtime`):** Az üzenetek és vezérlő jelek valós idejű szétosztásáért felelős WebSocket broker.
4. **Prompt Feldolgozó Kliens (`prompt.py`):** A háttérben futó Python vevő kód, amely feliratkozik az aktív beszélő üzeneteire, és átadja a kapott szöveget az LLM promptnak.

---


## 3. Csatornák és Elkülönített Jogosultsági Modell

A rendszer két teljesen eltérő típusú és jogosultságú csatornát használ a biztonságos beszélőváltás érdekében:

1. **Normál Pub/Sub Csatorna (`stt-{roomId}`):**
   * **Szerepe:** Ezen a csatornán áramlanak a rögzített beszéd-szöveg üzenetek és promptok.
   * **Jogosultság:** Normál Pub/Sub csatorna, amelyhez **minden felhasználónak (`user` és `master`) egyaránt van `publish` és `subscribe` joga**.

2. **LiveObject Vezérlő Csatorna (`stt-control-{roomId}`):**
   * **Szerepe:** Ez egy élő állapotszinkronizációs objektum (LiveObject), amely az aktív beszélő kijelölését (`active-floor`) tárolja és közvetíti.
   * **Jogosultság:** Szigorúan korlátozott csatorna! A **mezei felhasználó (`user`) kizárólag `subscribe` (olvasási/hallgatási) jogot kap**, így nem tudja átvenni a szót vagy felülírni a beszélő kilétét. Egyedül a `master` rendelkezik `publish` joggal erre az objektumra.

### 3.1. Beszédfelismerés (Web Speech API)
* A felismerést a böngésző natív `SpeechRecognition` / `webkitSpeechRecognition` API-ja végzi `hu-HU` nyelven.
* `interimResults = false`: Csak a véglegesített mondatok kerülnek elküldésre a halmozódó ismétlődések elkerülése érdekében.
* A felvétel a PTT gomb lenyomására (`touchstart`/`mousedown`) indul, és elengedésre (`touchend`/`mouseup`) áll le.

### 3.2. Haptikus Visszajelzés és Képernyő Ébrentartása
* **Rezgés:** A `navigator.vibrate()` segítségével a gomb megnyomásakor és elengedésekor haptikus visszajelzést ad (Androidon).
* **Screen Wake Lock:** A kijelző elalvását a `navigator.wakeLock` akadályozza meg. iOS Safari alatt ehhez egy rejtett, hurokba kötött némított videó nyújt kompatibilitási fallbacket.

---

## 4. Adatfolyam (Flow)

1. **Szoba beállítás és Jelenlét:**
   * A felhasználók megadják a nevüket a `user.html` felületen, és belépnek az Ably csatorna jelenléti listájára (`presence`).
   * A moderátor a `master.html` felületen látja a csatlakozott klienseket.

2. **Padlóvezérlés (Floor Control):**
   * A moderátor kiválaszt egy beszélőt -> A `master.html` publikálja az új aktív felhasználót az `stt-control-{roomId}` csatornára (`active-floor`).
   * A `user.html` és a `prompt.py` frissíti az aktív beszélő állapotát. A kijelölt `user.html`-en aktiválódik a TALK gomb.

3. **Beszéd rögzítése és Prompt továbbítása:**
   * A felhasználó nyomva tartja a gombot, beszél, majd elengedi.
   * A `user.html` véglegesíti a szöveget, és elküldi az Ably `speech` eseményére.
   * A `prompt.py` ellenőrzi, hogy a küldő egyezik-e az aktív beszélővel, majd fogadja és kinyeri a kész prompt szöveget.

## 5. Ably API Kulcsok és Jogosultságok Kezelése

A rendszer biztonságos és elkülönített működéséhez **két különálló Ably API kulcsot** kell létrehozni a [Dashboardon](https://ably.com/dashboard), amelyeket környezeti változókként (`environment variables`) kell átadni a Docker konténernek vagy a futtatókörnyezetnek:

* `ABLY_USER_KEY` (Kliens kulcs)
* `ABLY_MASTER_KEY` (Moderátori / Vezérlő kulcs)

---

### 5.1. Jogosultsági Mátrix (Capabilities)

| Kulcs Neve | Csatorna Minta | Jogosultságok (Capabilities) | Leírás / Szerepkör |
| :--- | :--- | :--- | :--- |
| **`ABLY_USER_KEY`** | `stt-*` | `publish`, `subscribe`, `presence` | **Normál Pub/Sub:** A mezei user küldhet és fogadhat prompt üzeneteket. |
| | `stt-control-*` | **`subscribe`** | **LiveObject:** A mezei user **CSAK OLVASHATJA** a beszélőváltás állapotát, módosítani nem tudja! |
| **`ABLY_MASTER_KEY`** | `stt-*` | `publish`, `subscribe`, `presence` | **Teljes Hozzáférés:** Módosíthatja a LiveObject állapotát és kezelheti a prompt csatornát is. |
| | `stt-control-*` | `publish`, `subscribe`, `presence` | |
---

### 5.3. Konténer Környezeti Változók (Environment Variables)

A Flask szerver indításakor és a Docker konténer futtatásakor az alábbi változókat kell megadni (pl. `.env` fájlban vagy `docker-compose.yml`-ben):

```yaml
# docker-compose.yml példa

services:
  control:
    build: .
    environment:
      - ABLY_ROOM_ID=default-room
      - ABLY_USER_KEY=xV3aDw.XXXXX:YYYYYYYYYYYYYYYY
      - ABLY_MASTER_KEY=xV3aDw.AAAAA:BBBBBBBBBBBBBBBB
```

## 6. Hálózati Elérés, Pinggy Tunneling és PWA Trükközés

A PWA (Progressive Web App) telepíthetőségének és a Web Speech API működésének szigorú előfeltétele a **HTTPS** kapcsolat. Mivel a webszerver egy belső/helyi hálózaton fut, a külső HTTPS elérést a **Pinggy** (SSH alagút) biztosítja.

### 6.1. Pinggy HTTPS Tunnel
* A `stt_master.py` indításakor egy reverse SSH alagutat nyit a Pinggy szolgáltatása felé (`ssh -p 443 -R0:localhost:PORT qr@a.pinggy.io`).
* Ez egy egyedi, publikus HTTPS URL-t ad (pl. `https://XXXXX.a.pinggy.link`).
* Ez a megoldás lehetővé teszi, hogy a mobiltelefonok biztonságos SSL/TLS kapcsolaton keresztül érjék el a helyi webszervert, ami elengedhetetlen a mikrofon és a PWA funkciókhoz.

### 6.2. PWA Telepítés és QR Kódos Csatlakozás
* **QR-kód Generálás:** A `stt_master.py` a Pinggy által adott publikus URL-ből és a szobaazonosítóból egy QR-kódot generál a terminálba és a vezérlő felületre. A felhasználóknak csak be kell olvasniuk ezt a mobillal a csatlakozáshoz.
* **PWA Trükközés:** A böngészők csak HTTPS protokoll felett engedik az alkalmazás kezdőképernyőre történő telepítését ("Add to Home Screen"). A Pinggy HTTPS alagútja mögé rejtett `manifest.json` és `service-worker.js` segítségével a `master.html` teljes értékű PWA-ként települ a telefonokra, így teljes képernyőn, böngészősávok nélkül fut.