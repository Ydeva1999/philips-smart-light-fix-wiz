# ⚡ WiZ-Rescue: 1-Click Auto-Discovery & Activation Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows | macOS | Linux | Android Termux](https://img.shields.io/badge/Platform-Cross--Platform-blue.svg)]()
[![Python: 3.6+](https://img.shields.io/badge/Python-3.6%2B-brightgreen.svg)]()
[![PowerShell: 5.1+](https://img.shields.io/badge/PowerShell-5.1%2B-blue.svg)]()
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero-success.svg)]()

> **⚠️ Don't return your Philips WiZ lights to Amazon or Flipkart!**  
> If your newly purchased Philips WiZ Smart LED Batten or Bulb connects to your Wi-Fi router but remains permanently stuck on **"Devices offline. Check your connection and try again"**, your hardware is completely healthy. You are experiencing an unhandled Dart type-cast bug in the official WiZ Connected v2 Flutter app.  
> **WiZ-Rescue** automatically discovers, repairs, and cloud-activates orphaned lights in **one click** over local UDP without requiring resets, developer mode, or third-party cloud bridges.

---

## 🎯 Targeted Hardware & Models

This tool is specifically engineered and tested for:
* **Primary Target Model:** **Philips 24W Smart Wi-Fi LED Batten**
  * **Model Number:** `LB0925`
  * **Product / Line Code:** `23096` (Astra Line Tunable White)
  * **Specifications:** 2400 Lumens, 2700K–6500K CCT Tunable White, 24W, 220–240V
  * **Manufacturer:** Signify Innovations India / Philips Lighting
* **Universal Compatibility:**
  * Philips WiZ Color & Tunable White Smart LED Bulbs (9W, 12W, B22, E27)
  * Philips WiZ Smart Downlights & Ceiling Fixtures
  * Any smart lighting fixture powered by the Signify ESP32 / ESP8266 WiZ firmware stack running local UDP port `38899`.

---

## 🔍 The Problem: Why Are Brand-New WiZ Lights Stuck "Offline"?

Hundreds of customer reviews on Amazon India, Flipkart, and Reddit report the identical failure pattern:
> *"The light successfully joins my 2.4GHz Wi-Fi router, but the WiZ Connected v2 app reaches 100% on the pairing screen and fails with 'Devices offline. Check your connection and try again.' Factory resetting the light 10 times and power-cycling the router changes nothing."*

### 🛠️ The Technical Root-Cause Analysis (Android / Flutter Stack Trace)
Inspection of the Android device `logcat` during the WiZ Connected v2 onboarding sequence reveals an unhandled Dart runtime type-cast exception:

```text
E/flutter: [ERROR:flutter/runtime/dart_vm_initializer.cc] Unhandled Exception: 
type 'SendingEncryptedCredential' is not a subtype of type 'ConnectingToDevice' in type cast
#0 DeviceOnboardingBloc._onPairingProgress (device_onboarding_bloc.dart:184)
...
ap pairing error: type 'SendingEncryptedCredential' is not a subtype of type 'ConnectingToDevice' in type cast
```

### 💥 The Chain Reaction:
1. **Wi-Fi Handshake Succeeds:** The WiZ app transmits your Wi-Fi SSID and password to the light's temporary soft-AP (`WiZConfig_xxxx`).
2. **IP Allocated:** The batten disconnects from AP mode, associates with your home router, and successfully obtains a local IP via DHCP.
3. **The Flutter Crash:** Immediately upon receiving confirmation that credentials were sent, the Flutter app crashes out of its onboarding state machine due to the type mismatch.
4. **The Missing Packet:** The app terminates BEFORE issuing the critical UDP `setSystemConfig` packet containing your account's **`homeId`**.
5. **The Orphaned State:** The light is running on your LAN with **`homeId = 0`**. Because its Home ID is unset, the Signify cloud broker refuses to map the light to your mobile app, leaving it stuck in a perpetual "Devices offline" zombie state.

---

## 🚀 The Solution: How WiZ-Rescue Works

WiZ devices run a lightweight, unencrypted local JSON-RPC server listening on UDP port `38899`. **WiZ-Rescue** bypasses the defective mobile onboarding pipeline:

```
+------------------+         Local UDP Broadcast (:38899)        +----------------------+
|                  | ----------------------------------------->  |                      |
|    WiZ-Rescue    |          getSystemConfig Probe              |  Healthy WiZ Light   |
|   (PC / Phone)   | <-----------------------------------------  |   (homeId: 12345678) |
|                  |            Extracts active Home ID          +----------------------+
|                  |
|                  |         Direct Unicast UDP (:38899)         +----------------------+
|                  | ----------------------------------------->  |                      |
|                  |       setSystemConfig: {"homeId": ...}      |  Orphaned WiZ Light  |
|                  |          setPilot: Visual Handshake         |    (homeId: 0 -> OK) |
+------------------+ <-----------------------------------------  +----------------------+
```

1. **Auto-Discovery:** Broadcasts `getSystemConfig` across your local subnet (`/24`) and inspects the local ARP table to penetrate router client isolation.
2. **Auto-Cloning:** Detects any existing working WiZ light on your network and automatically copies its valid `homeId` and `roomId`. *(If you have no other lights, you can input your Home ID directly).*
3. **Zero-Config Injection:** Sends targeted UDP packets directly to the orphaned light, permanently saving the Home ID into the light's NVRAM.
4. **Visual Handshake:** Triggers a rapid blink from Warm White (2700K) to Daylight (6500K) so you get instantaneous visual confirmation in your room that the light has been rescued.
5. **Instant App Sync:** Open your WiZ Connected app, and the light is immediately online, responsive, and ready for schedules and voice control.

---

## 💻 Quick Start (1-Minute Fix)

### Option A: Windows (1-Click, Zero Python Required)
1. Download or clone this repository to your Windows PC.
2. Ensure your PC is connected to the same Wi-Fi router as the light (2.4 GHz).
3. **Double-click `1-CLICK-WIZ-RESCUE.bat`**.
4. The tool uses native Windows PowerShell to detect your subnet, clone your Home ID, and activate the light automatically.

---

### Option B: Cross-Platform Python (Windows, macOS, Linux, Android Termux)
Works out-of-the-box with standard Python 3. **Zero third-party pip dependencies required.**

```bash
# Run auto-discovery and auto-repair:
python3 wiz_rescue.py

# Scan-only mode (inspect WiZ devices, IPs, and Home IDs without altering settings):
python3 wiz_rescue.py --scan-only

# Directly target a specific light IP:
python3 wiz_rescue.py --ip 192.168.1.50
```

#### Running on Android via Termux:
No PC needed! You can rescue lights directly from your Android phone connected to home Wi-Fi:
```bash
pkg install python git
git clone https://github.com/Ydeva1999/WiZ-Rescue.git
cd WiZ-Rescue
python wiz_rescue.py
```

---

## ⚙️ Advanced CLI Options

| Argument | Description | Example |
| :--- | :--- | :--- |
| `--ip <IP>` | Directly target a specific light's IP address (bypasses subnet broadcast) | `python3 wiz_rescue.py --ip 192.168.1.50` |
| `--home-id <ID>` | Manually specify the numeric WiZ Home ID | `python3 wiz_rescue.py --home-id 12345678` |
| `--room-id <ID>` | Manually specify the target Room ID | `python3 wiz_rescue.py --room-id 101` |
| `--scan-only` | Lists all discovered WiZ lights and their status without modifying anything | `python3 wiz_rescue.py --scan-only` |

---

## ❓ Frequently Asked Questions (FAQ)

### What if I don't have any existing working WiZ lights?
If this is your first WiZ light and there are no healthy lights on your network to auto-clone from:
1. Open the WiZ Connected v2 app, navigate to **Settings** > **Home Settings**.
2. Note down your numeric **Home ID**.
3. Run `python3 wiz_rescue.py` (the script will interactively prompt you for your Home ID) or pass it via `--home-id <ID>`.

### Does this void any warranty or require flashing custom firmware?
**No.** This tool uses the official, standard local UDP JSON-RPC protocol implemented by Signify in all WiZ products. It does not flash firmware, break tamper seals, or void warranties.

---

## 📜 License
Released under the [MIT License](LICENSE). Free for community, personal, and open-source usage.
