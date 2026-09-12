<#
.SYNOPSIS
    WiZ-Rescue: 1-Click Auto-Discovery & Cloud Activation Engine for Philips WiZ Lights
    Author: Devansh (@Ydeva1999)
    License: MIT
    
.DESCRIPTION
    Fixes the widespread Philips WiZ v2 Flutter app onboarding bug:
    "type 'SendingEncryptedCredential' is not a subtype of type 'ConnectingToDevice' in type cast"
    which leaves brand-new lights stuck in 'Devices offline' state with homeId = 0.
#>

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "     ⚡ WiZ-Rescue: 1-Click Auto-Fix & Cloud Activation Engine   " -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

$port = 38899
$udp = New-Object System.Net.Sockets.UdpClient
$udp.Client.ReceiveTimeout = 1500
$udp.EnableBroadcast = $true

# Discover local IP subnet dynamically
$localIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notmatch "Loopback|vEthernet|Tailscale" -and $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -notlike "127.*" } | Select-Object -First 1).IPAddress
if (-not $localIp) {
    Write-Host "[X] Could not automatically detect an active local network interface." -ForegroundColor Red
    $udp.Close()
    return
}
$subnetPrefix = $localIp.Substring(0, $localIp.LastIndexOf('.'))
Write-Host "[*] Active Local Subnet detected: $subnetPrefix.0/24" -ForegroundColor Gray

# Step 1: Scan for all WiZ lights
Write-Host "[*] Scanning network for all Philips WiZ lights..." -ForegroundColor Cyan

$discoveredDevices = @()
$broadcastEp = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse("$subnetPrefix.255"), $port)
$probeBytes = [System.Text.Encoding]::UTF8.GetBytes('{"method":"getSystemConfig","params":{}}')

# Send broadcast probe
try {
    [void]$udp.Send($probeBytes, $probeBytes.Length, $broadcastEp)
} catch {}

# Also probe recent ARP entries
$arpLines = (arp -a)
foreach ($line in $arpLines) {
    if ($line -match "($subnetPrefix\.\d+)\s+([a-f0-9\-]{17})") {
        $ip = $matches[1]
        try {
            $ep = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($ip), $port)
            [void]$udp.Send($probeBytes, $probeBytes.Length, $ep)
        } catch {}
    }
}

# Collect responses
$startTime = Get-Date
while ((Get-Date) -lt $startTime.AddSeconds(3)) {
    try {
        $remote = $null
        $respBytes = $udp.Receive([ref]$remote)
        $respStr = [System.Text.Encoding]::UTF8.GetString($respBytes)
        $json = $respStr | ConvertFrom-Json
        
        if ($json.result -and $json.result.mac) {
            $devIp = $remote.Address.ToString()
            if (-not ($discoveredDevices | Where-Object { $_.IP -eq $devIp })) {
                $discoveredDevices += [PSCustomObject]@{
                    IP = $devIp
                    MAC = $json.result.mac
                    HomeId = $json.result.homeId
                    RoomId = $json.result.roomId
                    Firmware = $json.result.fwVersion
                    Model = $json.result.moduleName
                }
            }
        }
    } catch {}
}

Write-Host "`n[*] Discovery Complete. Found $($discoveredDevices.Count) WiZ device(s):" -ForegroundColor Green
if ($discoveredDevices.Count -gt 0) {
    $discoveredDevices | Format-Table -AutoSize -Property IP, MAC, HomeId, RoomId, Model, Firmware
}

# Step 2: Determine Home ID
$healthyDevice = $discoveredDevices | Where-Object { $_.HomeId -gt 0 } | Select-Object -First 1
$orphanedDevices = $discoveredDevices | Where-Object { $_.HomeId -eq 0 }

$targetHomeId = 0
$targetRoomId = 0

if ($healthyDevice) {
    $targetHomeId = $healthyDevice.HomeId
    $targetRoomId = $healthyDevice.RoomId
    Write-Host "[+] Auto-Cloned credentials from healthy light ($($healthyDevice.IP)):" -ForegroundColor Green
    Write-Host "    -> Home ID : $targetHomeId" -ForegroundColor Yellow
    if ($targetRoomId -gt 0) {
        Write-Host "    -> Room ID : $targetRoomId" -ForegroundColor Yellow
    }
} else {
    Write-Host "[!] No existing active WiZ lights detected to auto-clone from." -ForegroundColor Yellow
    Write-Host "    (To find your Home ID: Open WiZ App > Settings > Home Settings)" -ForegroundColor Gray
    $inputVal = Read-Host "Enter your numeric WiZ Home ID"
    if ($inputVal -match '^\d+$') {
        $targetHomeId = [int]$inputVal
        $targetRoomId = 0
    } else {
        Write-Host "[X] Invalid Home ID entered. Exiting." -ForegroundColor Red
        $udp.Close()
        return
    }
}

# Step 3: Rescuing orphaned devices
if ($orphanedDevices.Count -eq 0) {
    Write-Host "`n[OK] All detected WiZ lights already have valid Home IDs!" -ForegroundColor Green
    Write-Host "    If you just plugged in a new light, make sure it has connected to Wi-Fi first." -ForegroundColor Gray
} else {
    Write-Host "`n[!] Found $($orphanedDevices.Count) orphaned light(s) with Home ID = 0!" -ForegroundColor Red
    
    foreach ($orphan in $orphanedDevices) {
        Write-Host "    -> Rescuing orphaned device at $($orphan.IP) (MAC: $($orphan.MAC))..." -ForegroundColor Cyan
        
        $payloadList = [System.Collections.Generic.List[string]]::new()
        $payloadList.Add((@{ method = 'setSystemConfig'; params = @{ homeId = $targetHomeId } } | ConvertTo-Json -Compress))
        if ($targetRoomId -gt 0) {
            $payloadList.Add((@{ method = 'setSystemConfig'; params = @{ homeId = $targetHomeId; roomId = $targetRoomId } } | ConvertTo-Json -Compress))
        }
        $payloadList.Add('{"method":"setPilot","params":{"state":true,"temp":2700,"dimming":100}}')
        $payloadList.Add('{"method":"setPilot","params":{"state":true,"temp":6500,"dimming":100}}')
        
        $orphanEp = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($orphan.IP), $port)
        
        foreach ($p in $payloadList) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($p)
            for ($k = 0; $k -lt 3; $k++) {
                [void]$udp.Send($bytes, $bytes.Length, $orphanEp)
                Start-Sleep -Milliseconds 60
            }
            Start-Sleep -Milliseconds 200
        }
        
        Write-Host "    [OK] Successfully injected Home ID $targetHomeId into $($orphan.IP)!" -ForegroundColor Green
    }
}

$udp.Close()
Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host " All done! Open your WiZ Connected app to verify." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
