#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_ue2.py - prampa build
===========================

Builds ``ue-v2-modified.luau.txt`` from ``ue-v2-cracked.luau.txt``.

What it changes
---------------
1. Rebrand
   - removes the ``--!nocheck`` / ``--!native`` directives
   - removes the huge ASCII-art banner comment at the top
   - replaces the Korean "free script" console banner with a branded one
   - renames the shared-env key ``Unnamed Enhancements - .gg/enhancements``
     to BRAND (both occurrences: the rawget guard and the assignment)

2. Title
   The two serialized constants ``[3166]`` / ``[7454]`` holding
   ``Unnamed Enhancements - .gg/enhancements`` are rewritten to MENU_TITLE.

3. Addon block (injected before the final ``return runApplication()``)
   - custom menu title (+ runtime fallback if the constants ever move)
   - "dynamic island" spawned centred at the top of the screen, 2 px down:
     Discord avatar / name / presence, FPS, ping, session uptime, local clock.
     While a song plays it also shows the track name and a progress hairline,
     and it drops stats one by one when the window is too narrow for all of
     them instead of growing past the edge of the screen.
   - click the island to open a glassy song card: cover tile, now-playing
     status, a seek bar you can drag, prev / play-pause / next, shuffle,
     per-track loop, live search, a draggable volume bar and a mute button
   - the card repaints from a Heartbeat tick, from the music callback and from
     the controls themselves, so the transport, loop, volume and time are
     always live even if one of those paths is missed
   - keyboard: Esc closes, / searches, up/down selects, Enter plays,
     Space pauses, left/right seeks 5 s, M mutes, L toggles loop
   - the island is dragged with relative pointer movement, so it follows the
     cursor even when the game has the mouse locked to the middle of the screen
   - optional corner watermark (wordmark only)
   - one track at a time: a finished song hands over to the next one, and the
     per-track loop is opt-in through the loop control

Music
-----
Roblox cannot stream an arbitrary https URL from a ``Sound``, so every track is
downloaded at runtime, written to the executor workspace and turned into an
asset with ``getcustomasset``.  That needs an executor with ``writefile`` and
``getcustomasset``; tracks are cached per URL afterwards.

MUSIC_TRACKS is a list of ``(title, file[, seconds])`` tuples, max 12.  ``file``
is either a name inside MUSIC_BASE, a full http(s) URL, or an ``rbxassetid://``
id.  The optional duration is only used to show the running time before a track
has ever been loaded; the real ``Sound.TimeLength`` takes over afterwards.

Clicking a title plays it, clicking it again restarts it from 0:00, and
selecting another one stops the previous track - there is a single ``Sound``
instance, so tracks can never overlap.  Playback fades in and out instead of
clicking.  The last played track autoplays on load.

Every song row has a small loop button next to it.  Loop is on by default for
each track; click the infinity button to toggle it for that song.  With loop
off, a finished song rolls on to the next one.  Shuffle replaces the "next"
track with a random one.  Volume, shuffle, last track, loop flags and the
dragged island position are saved to ``<BRAND>_config.json`` in the executor
workspace (only when ``writefile``/``readfile`` exist); mute is session-only.

Scripts can drive it through ``getgenv()``:
``UE_PlayTrack``, ``UE_SetTrackLoop``, ``UE_ToggleTrackLoop``, ``UE_NextTrack``,
``UE_PrevTrack``, ``UE_SeekTrack``, ``UE_SeekBy``, ``UE_ToggleTrack``,
``UE_ToggleShuffle``, ``UE_SetShuffle``, ``UE_ToggleMute``, ``UE_ToggleMusic``
and ``UE_SetMusicVolume``.

Set MUSIC_VOLUME to 1.0 for full volume; 0.25 is a quarter.

Roblox decodes MP3 (CBR/VBR) and OGG Vorbis only.  A ``.webm``/``.opus`` file
renamed to ``.mp3`` - what yt-dlp and most "youtube to mp3" sites hand you -
downloads fine but the client rejects it with

    Failed to load sound rbxasset://.../prampa_music_x.mp3: unsupported file format

Convert it first:

    ffmpeg -i in.webm -c:a libvorbis -q:a 5 out.ogg

Discord presence
----------------
Presence is not available from Discord's REST API and using a user token would
mean running a self-bot.  This uses Lanyard instead:

    1. join  https://discord.gg/lanyard  once
    2. put your numeric user ID in DISCORD_USER_ID

Usage
-----
    python patch_ue2.py
    python patch_ue2.py <source.txt> <output.txt>
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# EDIT THESE
# --------------------------------------------------------------------------

# Everything branded uses this: env key, watermark, console banner.
BRAND = "prampa"

MENU_TITLE = "Prampa Menu"

# Your numeric Discord user ID (17-20 digits), for Lanyard presence.
# Right click your name in Discord with Developer Mode on -> Copy User ID.
DISCORD_USER_ID = "1453886966599913708"

# Optional: force the displayed name instead of your Discord display name.
# Leave "" to use whatever Lanyard reports.
DISCORD_NAME = ""

# Island accent colour, RRGGBB.
ACCENT_HEX = "7C5CFF"

# Small "prampa" tag in the bottom-right corner.
SHOW_WATERMARK = True

# --------------------------------------------------------------------------
# background music / song picker
# --------------------------------------------------------------------------

# Folder the track files live in (must end with a slash).  A track's `file`
# may also be a full http(s) URL or an "rbxassetid://..." id, in which case
# this prefix is ignored.
MUSIC_BASE = "https://raw.githubusercontent.com/prampa/prampa-rivals/main/"

# (display title, file[, duration seconds]) - shown in the picker.
# At most 12 tracks.  Keep the .ogg files in the same folder as MUSIC_BASE.
# The duration is only used until the Sound reports its real length; it lets
# the list show track times before anything has been played.
MUSIC_TRACKS = [
    ("Panik Atak", "song.ogg", 147.3),
    ("Dönüyo Başım 2.0", "song1.ogg", 123.1),
    ("El clasico", "song2.ogg", 124.3),
    ("Fedakar", "song3.ogg", 207.9),
    ("Gömün Beni Çukura", "song4.ogg", 196.0),
    ("harbiden şekermiş", "song5.ogg", 165.1),
    ("Hoşuna mı Gidiyor", "song6.ogg", 151.9),
    ("Radyoda Neşet", "song7.ogg", 171.1),
]

# 0.25 = 25 % volume.
MUSIC_VOLUME = 0.25

# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------

OLD_TITLE = "Unnamed Enhancements - .gg/enhancements"

SOURCE_NAME = "ue-v2-cracked.luau.txt"
OUTPUT_NAME = "rivals_menu.luau"

# Same build, written under the name used on GitHub, so no manual copy is
# needed.  Set to "" to disable.
ALIAS_NAME = "rivals_menu.luau"

MARKER = "-- >>> prampa addon (patched by patch_ue2.py) >>>"
STALE_MARKERS = (
    "-- >>> UE v2 addon (patched by patch_ue2.py) >>>",
    MARKER,
)

PLACEHOLDER_ID = "[YOUR USER ID HERE]"
PLACEHOLDER_TITLE = "[YOUR TITLE HERE]"

# classic user token, and mfa tokens
TOKEN_RE = re.compile(
    r"^(?:mfa\.[A-Za-z0-9_-]{60,}"
    r"|[A-Za-z0-9_-]{20,32}\.[A-Za-z0-9_-]{5,10}\.[A-Za-z0-9_-]{25,60})$"
)


def lua_str(value: str) -> str:
    """Render *value* as a single-quoted Luau string literal."""
    out = (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\x00", "")
    )
    return "'" + out + "'"


def fail(message: str) -> "NoReturn":
    print("error: " + message, file=sys.stderr)
    raise SystemExit(1)


# The injected Luau block.  @@...@@ are replaced with already-quoted literals.
ADDON_TEMPLATE = r"""
-- >>> prampa addon (patched by patch_ue2.py) >>>
-- Menu title, branded HUD, Discord presence (Lanyard), FPS / ping, song picker.
do
    local BRAND = @@BRAND@@
    local ADDON_TITLE = @@TITLE@@
    local DISCORD_ID = @@DISCORD_ID@@
    local DISCORD_NAME_OVERRIDE = @@DISCORD_NAME@@
    local ACCENT = @@ACCENT@@
    local SHOW_WATERMARK = @@WATERMARK@@
    local MUSIC_BASE = @@MUSIC_BASE@@
    local MUSIC_TRACKS = @@MUSIC_TRACKS@@
    local MUSIC_VOLUME = @@MUSIC_VOLUME@@
    local BUILD_ID = @@BUILD_ID@@
    local POLL_SECONDS = 20

    local env = getgenv and getgenv() or _G
    local Players = game:GetService('Players')
    local RunService = game:GetService('RunService')
    local UserInputService = game:GetService('UserInputService')
    local HttpService = game:GetService('HttpService')
    local SoundService = game:GetService('SoundService')
    local TweenService = game:GetService('TweenService')
    local LocalPlayer = Players.LocalPlayer

    local ISLAND_NAME = 'prampa_HUD'
    local WATERMARK_NAME = 'prampa_Watermark'
    local LANYARD = 'https://api.lanyard.rest/v1/users/'
    local CDN = 'https://cdn.discordapp.com/'
    local CYAN = Color3.fromRGB(0, 208, 255)

    local STATUS_COLORS = {
        online = Color3.fromRGB(35, 165, 90),
        idle = Color3.fromRGB(240, 178, 50),
        dnd = Color3.fromRGB(242, 63, 67),
        offline = Color3.fromRGB(128, 132, 142),
        unknown = Color3.fromRGB(150, 150, 160),
    }

    -- printed before anything else, so the console always shows which build
    -- is running even if the HUD fails to construct
    env.prampa_BuildID = BUILD_ID
    print('[' .. BRAND .. '] build ' .. BUILD_ID .. ' starting (' .. tostring(#MUSIC_TRACKS) .. ' tracks)')

    -----------------------------------------------------------------------
    -- small helpers
    -----------------------------------------------------------------------

    local function guiParent()
        if type(gethui) == 'function' then
            local ok, hui = pcall(gethui)
            if ok and hui then
                return hui
            end
        end

        local ok, core = pcall(function()
            return game:GetService('CoreGui')
        end)
        if ok and core then
            return core
        end

        return LocalPlayer:WaitForChild('PlayerGui')
    end

    local function httpGet(url)
        local ok, body = pcall(function()
            return game:HttpGet(url)
        end)
        if ok and type(body) == 'string' and body ~= '' then
            return body
        end

        if type(request) == 'function' then
            local ok2, res = pcall(request, { Url = url, Method = 'GET' })
            if ok2 and type(res) == 'table' and type(res.Body) == 'string' then
                return res.Body
            end
        end

        if type(syn) == 'table' and type(syn.request) == 'function' then
            local ok3, res = pcall(syn.request, { Url = url, Method = 'GET' })
            if ok3 and type(res) == 'table' and type(res.Body) == 'string' then
                return res.Body
            end
        end

        return nil
    end

    local function looksLikeAudio(body)
        if type(body) ~= 'string' or #body < 12 then
            return false
        end

        if body:sub(1, 4) == 'OggS' then
            return true
        end
        if body:sub(1, 4) == 'RIFF' then
            return true
        end
        if body:sub(1, 3) == 'ID3' then
            return true
        end

        -- bare MPEG frame sync: 0xFF followed by 111xxxxx
        return body:byte(1) == 0xFF and body:byte(2) >= 0xE0
    end

    local function assetFromUrl(url, fileName, expectAudio)
        if type(getcustomasset) ~= 'function' or type(writefile) ~= 'function' then
            return nil
        end

        -- reuse a file that is already in the workspace; the names passed in
        -- are content-addressed (avatar hash / music url hash), so a cache hit
        -- can never serve a stale image or song
        local cached = false
        if type(isfile) == 'function' then
            local okFile, exists = pcall(isfile, fileName)
            cached = okFile and exists == true
        end

        -- a previous run may have cached a renamed .webm under this name;
        -- re-read it and throw it away unless it really is audio
        if cached and expectAudio and type(readfile) == 'function' then
            local okRead, content = pcall(readfile, fileName)
            if okRead and type(content) == 'string' and not looksLikeAudio(content) then
                cached = false
            end
        end

        if not cached then
            local body = httpGet(url)
            if type(body) ~= 'string' or body == '' then
                return nil
            end

            if expectAudio and not looksLikeAudio(body) then
                warn(
                    '[' .. BRAND .. '] ' .. fileName .. ' is not MP3/OGG/WAV '
                        .. '(a .webm/.opus file renamed to .mp3 is the usual '
                        .. 'cause). Convert it with: ffmpeg -i in.webm -c:a '
                        .. 'libvorbis out.ogg'
                )
                return nil
            end

            if not pcall(writefile, fileName, body) then
                return nil
            end
        end

        local ok, asset = pcall(getcustomasset, fileName)
        if ok and type(asset) == 'string' and asset ~= '' then
            return asset
        end

        return nil
    end

    local statsService
    local function readPing()
        if not statsService then
            local ok, service = pcall(function()
                return game:GetService('Stats')
            end)
            if ok then
                statsService = service
            end
        end
        if not statsService then
            return 0
        end

        local ok, item = pcall(function()
            return statsService.Network.ServerStatsItem['Data Ping']
        end)
        if not ok or not item then
            return 0
        end

        local ok2, value = pcall(function()
            return item:GetValue()
        end)
        if ok2 and type(value) == 'number' then
            return value
        end

        return 0
    end

    local function colorHex(color)
        return string.format(
            '#%02X%02X%02X',
            math.floor(color.R * 255 + 0.5),
            math.floor(color.G * 255 + 0.5),
            math.floor(color.B * 255 + 0.5)
        )
    end

    local function escapeRich(text)
        local value = tostring(text)
        value = value:gsub('&', '&amp;')
        value = value:gsub('<', '&lt;')
        value = value:gsub('>', '&gt;')
        return value
    end

    local function formatUptime(seconds)
        seconds = math.max(0, math.floor(seconds))

        local hours = math.floor(seconds / 3600)
        local minutes = math.floor((seconds % 3600) / 60)
        local secs = seconds % 60

        if hours > 0 then
            return string.format('%dh %02dm', hours, minutes)
        end

        return string.format('%02d:%02d', minutes, secs)
    end

    local function localClock()
        local ok, value = pcall(function()
            return DateTime.now():ToLocalTime():FormatLocalTime('HH:mm', 'en-us')
        end)
        if ok and type(value) == 'string' and value ~= '' then
            return value
        end

        local ok2, fallback = pcall(function()
            return os.date('%H:%M')
        end)
        if ok2 and type(fallback) == 'string' then
            return fallback
        end

        return '--:--'
    end

    -----------------------------------------------------------------------
    -- menu title
    -----------------------------------------------------------------------

    local function isMenuTitle(text)
        if type(text) ~= 'string' then
            return false
        end

        local lower = text:lower()
        return lower:find('unnamed enhancements', 1, true) ~= nil
    end

    local function guiRoots()
        local roots = {}

        if type(env.Library) == 'table' and typeof(env.Library.ScreenGui) == 'Instance' then
            table.insert(roots, env.Library.ScreenGui)
        end

        -- gethui() only covers the hidden layer.  the menu can be parented in
        -- PlayerGui, in which case nothing here would ever find it.
        local parents = { guiParent() }

        local okPlayer, playerGui = pcall(function()
            return LocalPlayer and LocalPlayer:FindFirstChild('PlayerGui')
        end)
        if okPlayer and playerGui then
            table.insert(parents, playerGui)
        end

        for _, parent in ipairs(parents) do
            if parent then
                local ok, children = pcall(function()
                    return parent:GetChildren()
                end)
                if ok then
                    for _, child in ipairs(children) do
                        if child:IsA('ScreenGui')
                            and child.Name ~= ISLAND_NAME
                            and child.Name ~= WATERMARK_NAME
                            and not table.find(roots, child) then
                            table.insert(roots, child)
                        end
                    end
                end
            end
        end

        return roots
    end

    local function applyTitle()
        local changed = false

        for _, gui in ipairs(guiRoots()) do
            local ok, descendants = pcall(function()
                return gui:GetDescendants()
            end)
            if ok then
                for _, obj in ipairs(descendants) do
                    if obj:IsA('TextLabel') and isMenuTitle(obj.Text) then
                        obj.Text = ADDON_TITLE
                        changed = true
                    end
                end
            end
        end

        return changed
    end

    local MENU_ORDER = 500000

    local function menuScreenGui()
        for _, gui in ipairs(guiRoots()) do
            local ok, descendants = pcall(function()
                return gui:GetDescendants()
            end)
            if ok then
                for _, obj in ipairs(descendants) do
                    if obj:IsA('TextLabel') and (isMenuTitle(obj.Text) or obj.Text == ADDON_TITLE) then
                        return gui
                    end
                end
            end
        end
        return nil
    end

    local function raiseMenu()
        local gui = menuScreenGui()
        if not gui then
            return false
        end
        if gui:GetAttribute('prampa_Raised') then
            return true
        end

        pcall(function()
            gui.DisplayOrder = MENU_ORDER
            gui:SetAttribute('prampa_Raised', true)
        end)

        local parent = guiParent()
        if parent then
            for _, child in ipairs(parent:GetChildren()) do
                if child.Name == ISLAND_NAME or child.Name == WATERMARK_NAME then
                    pcall(function()
                        child.DisplayOrder = MENU_ORDER + 10
                    end)
                end
            end
        end

        print('[' .. BRAND .. '] menu raised above overlays, display order ' .. MENU_ORDER)
        return true
    end

    local function watchTitle()
        task.spawn(function()
            for _ = 1, 480 do
                if applyTitle() then
                    return
                end
                task.wait(0.25)
            end
        end)

        task.spawn(function()
            while true do
                task.wait(2)

                if type(env.Library) == 'table'
                    and typeof(env.Library.ScreenGui) == 'Instance' then
                    local gui = env.Library.ScreenGui

                    if not gui:GetAttribute('prampa_TitleHook') then
                        gui:SetAttribute('prampa_TitleHook', true)

                        gui.DescendantAdded:Connect(function(obj)
                            if obj:IsA('TextLabel') then
                                task.defer(function()
                                    if obj.Parent and isMenuTitle(obj.Text) then
                                        obj.Text = ADDON_TITLE
                                    end
                                end)
                            end
                        end)
                    end

                    applyTitle()
                    raiseMenu()
                end
            end
        end)
    end

    -----------------------------------------------------------------------
    -- persisted settings
    --   tiny json file in the executor workspace: last track, volume,
    --   per-track loop flags and the dragged island position
    -----------------------------------------------------------------------

    local CONFIG_FILE = BRAND .. '_config.json'
    local config = {}
    local configToken = 0

    local function loadConfig()
        if type(readfile) ~= 'function' or type(isfile) ~= 'function' then
            return
        end

        local okFile, exists = pcall(isfile, CONFIG_FILE)
        if not okFile or not exists then
            return
        end

        local okRead, raw = pcall(readfile, CONFIG_FILE)
        if not okRead or type(raw) ~= 'string' or raw == '' then
            return
        end

        local okDecode, value = pcall(function()
            return HttpService:JSONDecode(raw)
        end)
        if okDecode and type(value) == 'table' then
            config = value
        end
    end

    local function saveConfig()
        if type(writefile) ~= 'function' then
            return
        end

        local okEncode, raw = pcall(function()
            return HttpService:JSONEncode(config)
        end)
        if okEncode and type(raw) == 'string' then
            pcall(writefile, CONFIG_FILE, raw)
        end
    end

    -- collapse bursts (volume scrubbing, loop toggles) into one write
    local function queueSave(seconds)
        configToken += 1
        local token = configToken

        task.delay(seconds or 0.4, function()
            if token == configToken then
                saveConfig()
            end
        end)
    end

    loadConfig()

    -----------------------------------------------------------------------
    -- background music controller
    --   one Sound instance is reused for every track, so tracks can never
    --   play on top of each other; selecting the current one restarts it
    -----------------------------------------------------------------------

    local music = {
        tracks = MUSIC_TRACKS,
        current = nil,
        sound = nil,
        assets = {},
        loop = {},
        volume = math.clamp(tonumber(config.volume) or MUSIC_VOLUME, 0, 1),
        -- mute is deliberately session-only: a saved mute would look like
        -- broken audio on the next load
        muted = false,
        shuffle = config.shuffle == true,
        fadeToken = 0,
        fadeTween = nil,
        -- playback state the sound itself cannot report
        paused = false,
        wasPlaying = false,
        playingSince = 0,
        advancedAt = 0,
    }

    -- what the Sound should actually be at right now
    function music.level()
        if music.muted then
            return 0
        end
        return music.volume
    end

    -- restore per-track loop settings (saved as a dense 1-based array)
    if type(config.loop) == 'table' then
        for index = 1, #MUSIC_TRACKS do
            local value = config.loop[index]
            if value ~= nil then
                music.loop[index] = value and true or false
            end
        end
    end

    local function trackSource(track)
        local file = track and track.file
        if type(file) ~= 'string' or file == '' then
            return nil
        end
        if file:find('://', 1, true) then
            return file
        end
        return MUSIC_BASE .. file
    end

    local function fileNameFor(source)
        local name = source:match('([^/]+)$') or 'track.ogg'
        name = name:gsub('[^%w%._-]', '_')

        -- deterministic hash so a changed url never reuses a stale file
        local hash = 7
        for index = 1, #source do
            hash = (hash * 31 + source:byte(index)) % 1000003
        end

        return string.format('prampa_%d_%s', hash, name)
    end

    local function saveLoopMask()
        config.loop = {}

        for index = 1, #music.tracks do
            config.loop[index] = music.isLooped(index)
        end

        queueSave()
    end

    local function prepareMusic()
        local sound = Instance.new('Sound')
        sound.Name = 'prampa_Music'
        sound.Looped = false
        sound.Volume = music.level()
        sound.Parent = SoundService

        music.sound = sound
        env.prampa_Music = sound

        sound.Ended:Connect(function()
            -- the track that just finished rolls on to the next one unless
            -- its own loop is on (a looped Sound never raises Ended)
            music.wasPlaying = false
            music.advance()
        end)

        -- watchdog: an Ended event can be missed when the executor swaps or
        -- streams the asset, so notice "was playing, no longer playing, not
        -- paused" as well.  It only fires after two seconds of real playback
        -- so the short idle moment while a track loads can never skip a song.
        RunService.Heartbeat:Connect(function()
            local active = music.sound
            if not active then
                return
            end

            if active.IsPlaying then
                if not music.wasPlaying then
                    music.wasPlaying = true
                    music.playingSince = os.clock()
                end
                return
            end

            if not music.wasPlaying or music.paused then
                return
            end

            if os.clock() - (music.playingSince or 0) < 2 then
                return
            end

            music.wasPlaying = false
            music.advance()
        end)
    end

    function music.isPlaying()
        return music.sound ~= nil and music.sound.IsPlaying == true
    end

    -- roll on to the next track after one finishes.  Ended and the heartbeat
    -- watchdog both call this, so the debounce stops a single finish from
    -- skipping two songs.
    function music.advance()
        if not music.current then
            return false
        end

        if os.clock() - (music.advancedAt or 0) < 0.75 then
            return false
        end

        music.advancedAt = os.clock()

        if music.isLooped(music.current) then
            return false
        end

        local target = music.nextIndex(1)
        if not target then
            return false
        end

        return music.play(target)
    end

    function music.isLooped(index)
        if not index then
            return false
        end

        -- loop is opt-in per track: by default a finished song hands over to
        -- the next one instead of repeating itself
        return music.loop[index] == true
    end

    function music.setLoop(index, value)
        if not music.tracks[index] then
            return false
        end

        music.loop[index] = value and true or false

        if music.current == index and music.sound then
            music.sound.Looped = music.loop[index]
        end

        saveLoopMask()

        if music.onChange then
            music.onChange()
        end

        return music.loop[index]
    end

    function music.toggleLoop(index)
        return music.setLoop(index, not music.isLooped(index))
    end

    function music.length(index)
        index = index or music.current
        if not index then
            return 0
        end

        if index == music.current and music.sound and music.sound.TimeLength > 0 then
            return music.sound.TimeLength
        end

        local track = music.tracks[index]
        return (track and tonumber(track.duration)) or 0
    end

    function music.position()
        if music.sound then
            return math.max(0, music.sound.TimePosition)
        end
        return 0
    end

    function music.fadeTo(target, duration, done)
        if not music.sound then
            return
        end

        target = math.clamp(target, 0, 1)
        music.fadeToken += 1
        local token = music.fadeToken

        -- one fade at a time: two live tweens on Volume would fight
        if music.fadeTween then
            music.fadeTween:Cancel()
            music.fadeTween = nil
        end

        music.fadeTween = TweenService:Create(
            music.sound,
            TweenInfo.new(math.max(0.01, duration), Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
            { Volume = target }
        )
        music.fadeTween:Play()

        if done then
            task.delay(math.max(0.01, duration), function()
                if token == music.fadeToken then
                    music.sound.Volume = target
                    done()
                end
            end)
        end
    end

    function music.seek(seconds)
        if not music.current or not music.sound then
            return false
        end

        local total = music.length(music.current)
        if total <= 0 then
            return false
        end

        music.sound.TimePosition = math.clamp(tonumber(seconds) or 0, 0, math.max(0, total - 0.05))

        if music.onChange then
            music.onChange()
        end

        return true
    end

    function music.nextIndex(delta)
        local count = #music.tracks
        if count == 0 then
            return nil
        end

        if not music.current then
            return 1
        end

        delta = delta or 1

        -- shuffle only changes what comes *next*; going back stays literal
        if delta > 0 and music.shuffle and count > 1 then
            local pick = music.current

            for _ = 1, 16 do
                pick = math.random(1, count)
                if pick ~= music.current then
                    break
                end
            end

            return pick
        end

        local target = music.current + delta
        if target < 1 then
            target = count
        elseif target > count then
            target = 1
        end

        return target
    end

    function music.step(delta)
        local target = music.nextIndex(delta)
        if not target then
            return false
        end

        return music.play(target)
    end

    function music.seekBy(delta)
        if not music.current then
            return false
        end

        return music.seek(music.position() + (tonumber(delta) or 0))
    end

    function music.play(index)
        local track = music.tracks[index]
        if not track or not music.sound then
            return false
        end

        music.paused = false
        music.wasPlaying = false
        music.playingSince = 0

        -- clicking the current track restarts it instead of layering a copy
        if music.current == index and music.sound.SoundId ~= '' then
            music.sound.Looped = music.isLooped(index)
            music.sound.TimePosition = 0
            music.sound.Volume = 0
            music.sound:Play()
            music.fadeTo(music.level(), 0.2)

            if music.onChange then
                music.onChange()
            end
            return true
        end

        local asset = music.assets[index]
        if asset == nil then
            local source = trackSource(track)
            asset = source and assetFromUrl(source, fileNameFor(source), true) or false
            music.assets[index] = asset
        end

        if not asset then
            warn('[' .. BRAND .. '] could not load "' .. tostring(track.title) .. '"')
            return false
        end

        -- stop the old track first so two songs can never overlap
        music.sound:Stop()
        music.sound.Looped = music.isLooped(index)
        music.sound.SoundId = asset
        music.sound.TimePosition = 0
        music.sound.Volume = 0
        music.sound:Play()

        music.current = index
        music.fadeTo(music.level(), 0.25)

        config.track = index
        queueSave()

        if music.onChange then
            music.onChange()
        end

        return true
    end

    function music.toggle()
        if not music.sound then
            return false
        end

        if music.sound.IsPlaying then
            music.paused = true

            music.fadeTo(0, 0.14, function()
                if music.paused and music.sound then
                    music.sound:Pause()
                end

                if music.sound then
                    music.sound.Volume = music.level()
                end

                if music.onChange then
                    music.onChange()
                end
            end)
        elseif music.current then
            music.sound.Volume = 0

            -- Resume, not Play: Play on a paused Sound starts it again from
            -- 0:00, which made pausing look like a restart
            if music.paused then
                music.sound:Resume()
            else
                music.sound:Play()
            end

            music.paused = false
            music.wasPlaying = true
            music.playingSince = os.clock()
            music.fadeTo(music.level(), 0.2)
        elseif #music.tracks > 0 then
            music.play(1)
        end

        if music.onChange then
            music.onChange()
        end

        return music.isPlaying()
    end

    function music.setVolume(value)
        local number = tonumber(value)
        if not number then
            return music.volume
        end

        music.volume = math.clamp(number, 0, 1)
        music.muted = false
        music.fadeToken += 1

        if music.fadeTween then
            music.fadeTween:Cancel()
            music.fadeTween = nil
        end

        if music.sound then
            music.sound.Volume = music.level()
        end

        config.volume = music.volume
        queueSave()

        if music.onChange then
            music.onChange()
        end

        return music.volume
    end

    function music.setMuted(value)
        music.muted = value and true or false
        music.fadeToken += 1

        if music.fadeTween then
            music.fadeTween:Cancel()
            music.fadeTween = nil
        end

        if music.sound then
            music.sound.Volume = music.level()
        end

        if music.onChange then
            music.onChange()
        end

        return music.muted
    end

    function music.toggleMute()
        return music.setMuted(not music.muted)
    end

    function music.setShuffle(value)
        music.shuffle = value and true or false
        config.shuffle = music.shuffle
        queueSave()

        if music.onChange then
            music.onChange()
        end

        return music.shuffle
    end

    function music.toggleShuffle()
        return music.setShuffle(not music.shuffle)
    end

    -----------------------------------------------------------------------
    -- island
    -----------------------------------------------------------------------

    local function buildIsland()
        local screenGui = Instance.new('ScreenGui')
        screenGui.Name = ISLAND_NAME
        screenGui.ResetOnSpawn = false
        screenGui.IgnoreGuiInset = true
        screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
        screenGui.DisplayOrder = 999999
        screenGui.Parent = guiParent()

        -- full-size transparent frame: its AbsolutePosition is the gui origin,
        -- which is the only reliable way to turn an absolute screen position
        -- into a child offset when the executor applies its own inset
        local hudRoot = Instance.new('Frame')
        hudRoot.Name = 'HudRoot'
        hudRoot.BackgroundTransparency = 1
        hudRoot.BorderSizePixel = 0
        hudRoot.Size = UDim2.fromScale(1, 1)
        hudRoot.Position = UDim2.fromOffset(0, 0)
        hudRoot.ZIndex = 0
        hudRoot.Parent = screenGui

        local island = Instance.new('Frame')
        island.Name = 'Island'
        -- centred horizontally, 2 px below the top edge of the screen
        island.AnchorPoint = Vector2.new(0.5, 0)
        island.Position = UDim2.new(0.5, 0, 0, 2)
        island.Size = UDim2.fromOffset(0, 34)
        island.AutomaticSize = Enum.AutomaticSize.X
        island.BackgroundColor3 = Color3.fromRGB(15, 15, 18)
        island.BackgroundTransparency = 0.12
        island.BorderSizePixel = 0
        island.Active = true
        island.ClipsDescendants = true
        island.ZIndex = 10
        island.Parent = screenGui

        -- restore a dragged position from a previous run (offset based)
        local savedPosition = env.UE_ISLAND_POSITION
        if typeof(savedPosition) == 'UDim2' then
            island.AnchorPoint = Vector2.new(0, 0)
            island.Position = savedPosition
        elseif type(config.island) == 'table'
            and type(config.island.x) == 'number'
            and type(config.island.y) == 'number' then
            island.AnchorPoint = Vector2.new(0, 0)
            island.Position = UDim2.fromOffset(
                math.max(0, config.island.x),
                math.max(0, config.island.y)
            )
        end

        local corner = Instance.new('UICorner')
        corner.CornerRadius = UDim.new(1, 0)
        corner.Parent = island

        local stroke = Instance.new('UIStroke')
        stroke.Color = ACCENT
        stroke.Transparency = 0.6
        stroke.Thickness = 1
        stroke.Parent = island

        local gradient = Instance.new('UIGradient')
        gradient.Rotation = 90
        gradient.Color = ColorSequence.new({
            ColorSequenceKeypoint.new(0, Color3.fromRGB(35, 35, 42)),
            ColorSequenceKeypoint.new(1, Color3.fromRGB(15, 15, 18)),
        })
        gradient.Parent = island

        local padding = Instance.new('UIPadding')
        padding.PaddingLeft = UDim.new(0, 10)
        padding.PaddingRight = UDim.new(0, 12)
        padding.PaddingTop = UDim.new(0, 6)
        padding.PaddingBottom = UDim.new(0, 6)
        padding.Parent = island

        local layout = Instance.new('UIListLayout')
        layout.FillDirection = Enum.FillDirection.Horizontal
        layout.SortOrder = Enum.SortOrder.LayoutOrder
        layout.VerticalAlignment = Enum.VerticalAlignment.Center
        layout.HorizontalAlignment = Enum.HorizontalAlignment.Center
        layout.Padding = UDim.new(0, 9)
        layout.Parent = island

        local avatarHolder = Instance.new('Frame')
        avatarHolder.Name = 'AvatarHolder'
        avatarHolder.BackgroundTransparency = 1
        avatarHolder.Size = UDim2.fromOffset(20, 20)
        avatarHolder.LayoutOrder = 0
        avatarHolder.Parent = island

        local avatar = Instance.new('ImageLabel')
        avatar.Name = 'Avatar'
        avatar.BackgroundColor3 = STATUS_COLORS.unknown
        avatar.BorderSizePixel = 0
        avatar.Size = UDim2.fromScale(1, 1)
        avatar.ImageTransparency = 1
        avatar.Parent = avatarHolder

        local avatarCorner = Instance.new('UICorner')
        avatarCorner.CornerRadius = UDim.new(1, 0)
        avatarCorner.Parent = avatar

        local dot = Instance.new('Frame')
        dot.Name = 'LiveDot'
        dot.AnchorPoint = Vector2.new(1, 1)
        dot.Position = UDim2.fromScale(1, 1)
        dot.BackgroundColor3 = STATUS_COLORS.unknown
        dot.BorderSizePixel = 0
        dot.Size = UDim2.fromOffset(9, 9)
        dot.ZIndex = 3
        dot.Visible = false
        dot.Parent = avatarHolder

        local dotCorner = Instance.new('UICorner')
        dotCorner.CornerRadius = UDim.new(1, 0)
        dotCorner.Parent = dot

        local dotStroke = Instance.new('UIStroke')
        dotStroke.Color = Color3.fromRGB(15, 15, 18)
        dotStroke.Thickness = 2
        dotStroke.Parent = dot

        local function makeLabel(name, text, color, order)
            local label = Instance.new('TextLabel')
            label.Name = name
            label.BackgroundTransparency = 1
            label.Size = UDim2.fromOffset(0, 20)
            label.AutomaticSize = Enum.AutomaticSize.X
            label.Font = Enum.Font.GothamMedium
            label.TextSize = 13
            label.TextColor3 = color
            label.Text = text
            label.TextXAlignment = Enum.TextXAlignment.Left
            label.LayoutOrder = order
            label.Parent = island
            return label
        end

        local nameLabel = makeLabel('DiscordLabel', 'discord  not linked', Color3.fromRGB(220, 220, 230), 1)
        nameLabel.RichText = true

        -- song waves, only animate while something is playing ---------------
        local waveHolder = Instance.new('Frame')
        waveHolder.Name = 'Waves'
        waveHolder.BackgroundTransparency = 1
        waveHolder.Size = UDim2.fromOffset(16, 14)
        waveHolder.LayoutOrder = 2
        waveHolder.Visible = false
        waveHolder.Parent = island

        local waveBars = {}
        for index = 1, 4 do
            local bar = Instance.new('Frame')
            bar.Name = 'Bar' .. index
            bar.BackgroundColor3 = ACCENT
            bar.BackgroundTransparency = 0.15
            bar.BorderSizePixel = 0
            bar.AnchorPoint = Vector2.new(0, 1)
            bar.Position = UDim2.fromOffset((index - 1) * 4, 14)
            bar.Size = UDim2.fromOffset(2, 3)
            bar.Parent = waveHolder

            local barCorner = Instance.new('UICorner')
            barCorner.CornerRadius = UDim.new(1, 0)
            barCorner.Parent = bar

            waveBars[index] = bar
        end

        local function makeSeparator(order)
            local sep = Instance.new('Frame')
            sep.Name = 'Separator'
            sep.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
            sep.BackgroundTransparency = 0.8
            sep.BorderSizePixel = 0
            sep.Size = UDim2.fromOffset(1, 14)
            sep.LayoutOrder = order
            sep.Parent = island
            return sep
        end

        local sep1 = makeSeparator(4)
        local fpsLabel = makeLabel('FPSLabel', '0 FPS', Color3.fromRGB(220, 220, 230), 5)
        local sep2 = makeSeparator(6)
        local pingLabel = makeLabel('PingLabel', '-- MS', Color3.fromRGB(220, 220, 230), 7)
        local sep3 = makeSeparator(8)
        local uptimeLabel = makeLabel('UptimeLabel', '00:00', Color3.fromRGB(170, 170, 182), 9)
        local sep4 = makeSeparator(10)
        local clockLabel = makeLabel('ClockLabel', '--:--', Color3.fromRGB(170, 170, 182), 11)

        -- now playing: the track name in the island plus a hairline of progress
        local songLabel = makeLabel('SongLabel', '', ACCENT, 3)
        songLabel.TextSize = 12
        -- grow with the title (no dead space after short names) but never past
        -- the cap, which keeps a long title from stretching the island
        songLabel.AutomaticSize = Enum.AutomaticSize.X
        songLabel.TextTruncate = Enum.TextTruncate.AtEnd
        songLabel.Visible = false

        local songLimit = Instance.new('UISizeConstraint')
        songLimit.MaxSize = Vector2.new(150, 20)
        songLimit.Parent = songLabel

        -- the hairline lives outside the island: a UIListLayout would place any
        -- direct child in the row instead of letting it sit on the bottom edge
        local progressTrack = Instance.new('Frame')
        progressTrack.Name = 'IslandProgressTrack'
        progressTrack.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
        progressTrack.BackgroundTransparency = 0.88
        progressTrack.BorderSizePixel = 0
        progressTrack.Size = UDim2.fromOffset(0, 2)
        progressTrack.ZIndex = 11
        progressTrack.Visible = false
        progressTrack.Parent = screenGui

        local trackCorner = Instance.new('UICorner')
        trackCorner.CornerRadius = UDim.new(1, 0)
        trackCorner.Parent = progressTrack

        local progressLine = Instance.new('Frame')
        progressLine.Name = 'IslandProgress'
        progressLine.BackgroundColor3 = ACCENT
        progressLine.BackgroundTransparency = 0.12
        progressLine.BorderSizePixel = 0
        progressLine.Size = UDim2.fromOffset(0, 2)
        progressLine.ZIndex = 12
        progressLine.Visible = false
        progressLine.Parent = screenGui

        local lineCorner = Instance.new('UICorner')
        lineCorner.CornerRadius = UDim.new(1, 0)
        lineCorner.Parent = progressLine

        -- the island is automatic-width, so on small screens the stats are
        -- dropped one at a time until it fits again
        local islandGroups = {
            { clockLabel, sep4 },
            { uptimeLabel, sep3 },
            { pingLabel, sep2 },
            { fpsLabel, sep1 },
        }
        local islandFitToken = 0
        local songAllowed = true
        local compactPresence = false
        local redrawPresence = function() end
        local fitSignature = nil

        -- applying a fit is instant and does not repaint the row, so it can be
        -- reused whenever the content has not changed.  That keeps the polling
        -- loop from flashing the stats on and off every couple of seconds.
        local function applyFit(hiddenGroups, compact, song)
            for index, item in ipairs(islandGroups) do
                local visible = index > hiddenGroups
                item[1].Visible = visible
                item[2].Visible = visible
            end

            if compactPresence ~= compact then
                compactPresence = compact
                redrawPresence()
            end

            songAllowed = song
            songLabel.Visible = song and music.current ~= nil
        end

        local function fitIsland()
            islandFitToken += 1
            local token = islandFitToken

            task.spawn(function()
                local camera = workspace.CurrentCamera
                local viewport = camera and camera.ViewportSize or Vector2.new(1920, 1080)
                local limit = math.max(180, viewport.X - 26)

                local current = music.current
                local track = current and music.tracks[current] or nil
                local signature = tostring(nameLabel.Text) .. '|'
                    .. (track and track.title or '') .. '|'
                    .. tostring(math.floor(viewport.X))

                if signature == fitSignature then
                    return
                end

                -- measure from the most complete state, then drop pieces until
                -- the island fits inside the screen
                applyFit(0, false, true)
                task.wait()

                local hidden = 0
                for _ = 1, #islandGroups do
                    if token ~= islandFitToken then
                        return
                    end
                    if island.AbsoluteSize.X <= limit then
                        break
                    end

                    hidden += 1
                    applyFit(hidden, false, true)
                    task.wait()
                end

                local compact = false

                if token == islandFitToken and island.AbsoluteSize.X > limit then
                    compact = true
                    applyFit(hidden, true, true)
                    task.wait()
                end

                local song = true

                if token == islandFitToken and island.AbsoluteSize.X > limit then
                    song = false
                    applyFit(hidden, compact, false)
                end

                if token == islandFitToken then
                    fitSignature = signature
                end
            end)
        end

        -----------------------------------------------------------------------
        -- song picker (opens instead of collapsing the island)
        -----------------------------------------------------------------------

        -- built inside a pcall: if anything here throws, the island keeps its
        -- clock, stats and waves instead of silently dying
        local togglePanel = function() end
        local syncPanel = function() end
        local closePanel = function() end

        local pickerOk, pickerError = pcall(function()

        local PANEL_WIDTH = 322
        local PAD = 12
        local HEADER_HEIGHT = 44
        local PROGRESS_HEIGHT = 26
        local TRANSPORT_HEIGHT = 28
        local SEARCH_HEIGHT = 28
        local ROW_HEIGHT = 34
        local ROW_GAP = 3
        local FOOTER_HEIGHT = 16
        local SEARCH_TOP = PAD + HEADER_HEIGHT + 10 + PROGRESS_HEIGHT + 6 + TRANSPORT_HEIGHT + 8
        local LIST_TOP = SEARCH_TOP + SEARCH_HEIGHT + 8
        local CHROME = LIST_TOP + 8 + FOOTER_HEIGHT + PAD

        local TEXT_IDLE = Color3.fromRGB(207, 207, 220)
        local TEXT_ACTIVE = Color3.fromRGB(255, 255, 255)
        local TEXT_MUTED = Color3.fromRGB(142, 142, 158)
        local TEXT_DIM = Color3.fromRGB(114, 114, 130)
        local ROW_TINT = Color3.fromRGB(255, 255, 255)
        local DANGER = Color3.fromRGB(255, 142, 142)

        local panelOpen = false
        local panelTween
        local panelBelow = true
        local dropletToken = 0
        local selected = music.current or 1
        local loadingIndex = nil
        local failedTitle = nil
        local eqPhase = 0
        local scrubbing = false
        local scrubFraction = nil
        local volumeDragging = false

        -- a full-screen invisible frame: its AbsolutePosition is the gui
        -- origin, which is the only reliable way to convert the island's
        -- screen position into a child offset (the gui inset moves one but
        -- not the other depending on executor settings).  hudRoot already
        -- serves that purpose, so the card reuses it.
        local root = hudRoot

        -- forward declarations: row handlers are connected before the
        -- implementations below exist
        local applyRowStyle
        local refreshRows
        local updateHeader
        local updateProgress
        local updateVolume
        local animateRows
        local loadAndPlay
        local scrollToSelected
        local syncUI

        local connections = {}
        local function bind(signal, handler)
            local connection = signal:Connect(handler)
            connections[#connections + 1] = connection
            return connection
        end

        local function isPrimary(input)
            return input.UserInputType == Enum.UserInputType.MouseButton1
                or input.UserInputType == Enum.UserInputType.Touch
        end

        local function formatTime(seconds)
            seconds = math.max(0, math.floor((tonumber(seconds) or 0) + 0.5))
            return string.format('%d:%02d', math.floor(seconds / 60), seconds % 60)
        end

        local function coverColors(index)
            local hue = (0.66 + (index - 1) * 0.038) % 1
            local base = Color3.fromHSV(hue, 0.52, 0.9)
            return base, base:Lerp(Color3.new(0, 0, 0), 0.5)
        end

        -- click-outside catcher.  It sits below the island (ZIndex 10), so
        -- clicking the island still toggles the panel instead of closing it.
        local overlay = Instance.new('TextButton')
        overlay.Name = 'SongPickerOverlay'
        overlay.BackgroundTransparency = 1
        overlay.BorderSizePixel = 0
        overlay.Size = UDim2.fromScale(1, 1)
        overlay.Text = ''
        overlay.AutoButtonColor = false
        overlay.Visible = false
        overlay.ZIndex = 4
        overlay.Parent = screenGui

        local panel = Instance.new('Frame')
        panel.Name = 'SongPicker'
        panel.AnchorPoint = Vector2.new(0.5, 0)
        panel.Position = UDim2.new(0.5, 0, 0, 42)
        panel.Size = UDim2.fromOffset(PANEL_WIDTH, 0)
        panel.BackgroundColor3 = Color3.fromRGB(13, 13, 17)
        panel.BackgroundTransparency = 0.06
        panel.BorderSizePixel = 0
        panel.ClipsDescendants = true
        panel.Active = true
        panel.Visible = false
        panel.ZIndex = 5
        panel.Parent = screenGui

        local panelCorner = Instance.new('UICorner')
        panelCorner.CornerRadius = UDim.new(1, 0)
        panelCorner.Parent = panel

        local panelStroke = Instance.new('UIStroke')
        panelStroke.Color = ACCENT
        panelStroke.Transparency = 0.42
        panelStroke.Thickness = 1
        panelStroke.Parent = panel

        local panelGradient = Instance.new('UIGradient')
        panelGradient.Rotation = 90
        panelGradient.Color = ColorSequence.new({
            ColorSequenceKeypoint.new(0, Color3.fromRGB(38, 38, 49)),
            ColorSequenceKeypoint.new(0.5, Color3.fromRGB(21, 21, 28)),
            ColorSequenceKeypoint.new(1, Color3.fromRGB(11, 11, 15)),
        })
        panelGradient.Parent = panel

        -- faint inner sheen so the card reads as glass instead of a flat box
        local glass = Instance.new('Frame')
        glass.Name = 'Glass'
        glass.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
        glass.BackgroundTransparency = 0.985
        glass.BorderSizePixel = 0
        glass.Size = UDim2.fromScale(1, 1)
        glass.ZIndex = 1
        glass.Parent = panel

        local glassCorner = Instance.new('UICorner')
        glassCorner.CornerRadius = UDim.new(1, 0)
        glassCorner.Parent = glass

        -- the liquid bloom that spills out of the island when opening
        local ripple = Instance.new('Frame')
        ripple.Name = 'Ripple'
        ripple.AnchorPoint = Vector2.new(0.5, 0)
        ripple.Position = UDim2.new(0.5, 0, 0, 0)
        ripple.BackgroundColor3 = ACCENT
        ripple.BackgroundTransparency = 1
        ripple.BorderSizePixel = 0
        ripple.Size = UDim2.fromOffset(40, 40)
        ripple.ZIndex = 1
        ripple.Parent = panel

        local rippleCorner = Instance.new('UICorner')
        rippleCorner.CornerRadius = UDim.new(1, 0)
        rippleCorner.Parent = ripple

        -- a glass droplet that falls out of the island and melts into the card
        local droplet = Instance.new('Frame')
        droplet.Name = 'Droplet'
        droplet.AnchorPoint = Vector2.new(0.5, 0)
        droplet.BackgroundColor3 = ACCENT
        droplet.BackgroundTransparency = 1
        droplet.BorderSizePixel = 0
        droplet.Size = UDim2.fromOffset(12, 12)
        droplet.ZIndex = 6
        droplet.Visible = false
        droplet.Parent = screenGui

        local dropletCorner = Instance.new('UICorner')
        dropletCorner.CornerRadius = UDim.new(1, 0)
        dropletCorner.Parent = droplet

        local dropletStroke = Instance.new('UIStroke')
        dropletStroke.Color = Color3.fromRGB(225, 215, 255)
        dropletStroke.Transparency = 1
        dropletStroke.Thickness = 1
        dropletStroke.Parent = droplet

        -- header: cover tile, song title, live status, close -----------------
        local header = Instance.new('Frame')
        header.Name = 'Header'
        header.BackgroundTransparency = 1
        header.Position = UDim2.fromOffset(PAD, PAD)
        header.Size = UDim2.new(1, -PAD * 2, 0, HEADER_HEIGHT)
        header.ZIndex = 2
        header.Parent = panel

        local cover = Instance.new('Frame')
        cover.Name = 'Cover'
        cover.Position = UDim2.fromOffset(0, 1)
        cover.Size = UDim2.fromOffset(38, 38)
        cover.BackgroundColor3 = ACCENT
        cover.BorderSizePixel = 0
        cover.ZIndex = 3
        cover.Parent = header

        local coverCorner = Instance.new('UICorner')
        coverCorner.CornerRadius = UDim.new(0, 11)
        coverCorner.Parent = cover

        local coverGradient = Instance.new('UIGradient')
        coverGradient.Rotation = 135
        coverGradient.Color = ColorSequence.new(
            ACCENT,
            ACCENT:Lerp(Color3.new(0, 0, 0), 0.5)
        )
        coverGradient.Parent = cover

        local coverStroke = Instance.new('UIStroke')
        coverStroke.Color = Color3.fromRGB(255, 255, 255)
        coverStroke.Transparency = 0.8
        coverStroke.Thickness = 1
        coverStroke.Parent = cover

        local coverNumber = Instance.new('TextLabel')
        coverNumber.Name = 'CoverNumber'
        coverNumber.BackgroundTransparency = 1
        coverNumber.Size = UDim2.fromScale(1, 1)
        coverNumber.Font = Enum.Font.GothamBold
        coverNumber.TextSize = 13
        coverNumber.TextColor3 = Color3.fromRGB(255, 255, 255)
        coverNumber.Text = '01'
        coverNumber.ZIndex = 4
        coverNumber.Parent = cover

        local titleLabel = Instance.new('TextLabel')
        titleLabel.Name = 'Title'
        titleLabel.BackgroundTransparency = 1
        titleLabel.Position = UDim2.fromOffset(48, -1)
        titleLabel.Size = UDim2.new(1, -48 - 30, 0, 20)
        titleLabel.Font = Enum.Font.GothamBold
        titleLabel.TextSize = 14
        titleLabel.TextColor3 = TEXT_ACTIVE
        titleLabel.TextXAlignment = Enum.TextXAlignment.Left
        titleLabel.TextTruncate = Enum.TextTruncate.AtEnd
        titleLabel.Text = 'Music'
        titleLabel.ZIndex = 3
        titleLabel.Parent = header

        local statusLabel = Instance.new('TextLabel')
        statusLabel.Name = 'Status'
        statusLabel.BackgroundTransparency = 1
        statusLabel.Position = UDim2.fromOffset(48, 19)
        statusLabel.Size = UDim2.new(1, -48 - 30, 0, 16)
        statusLabel.Font = Enum.Font.GothamMedium
        statusLabel.TextSize = 11
        statusLabel.TextColor3 = TEXT_MUTED
        statusLabel.TextXAlignment = Enum.TextXAlignment.Left
        statusLabel.TextTruncate = Enum.TextTruncate.AtEnd
        statusLabel.Text = 'choose a song'
        statusLabel.ZIndex = 3
        statusLabel.Parent = header

        local closeButton = Instance.new('TextButton')
        closeButton.Name = 'Close'
        closeButton.AnchorPoint = Vector2.new(1, 0)
        closeButton.Position = UDim2.new(1, 0, 0, -4)
        closeButton.Size = UDim2.fromOffset(30, 30)
        closeButton.BackgroundColor3 = ROW_TINT
        closeButton.BackgroundTransparency = 1
        closeButton.BorderSizePixel = 0
        closeButton.Font = Enum.Font.GothamBold
        closeButton.TextSize = 17
        closeButton.TextColor3 = TEXT_MUTED
        closeButton.Text = '×'
        closeButton.AutoButtonColor = false
        closeButton.ZIndex = 3
        closeButton.Parent = header

        local closeCorner = Instance.new('UICorner')
        closeCorner.CornerRadius = UDim.new(0, 9)
        closeCorner.Parent = closeButton

        -- progress ---------------------------------------------------------
        local progressTop = PAD + HEADER_HEIGHT + 10
        local progressButton = Instance.new('TextButton')
        progressButton.Name = 'Progress'
        progressButton.BackgroundTransparency = 1
        progressButton.BorderSizePixel = 0
        progressButton.Position = UDim2.fromOffset(PAD, progressTop)
        progressButton.Size = UDim2.new(1, -PAD * 2, 0, 14)
        progressButton.Text = ''
        progressButton.AutoButtonColor = false
        progressButton.ZIndex = 3
        progressButton.Parent = panel

        local rail = Instance.new('Frame')
        rail.Name = 'Rail'
        rail.AnchorPoint = Vector2.new(0, 0.5)
        rail.Position = UDim2.new(0, 0, 0.5, 0)
        rail.Size = UDim2.new(1, 0, 0, 4)
        rail.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
        rail.BackgroundTransparency = 0.86
        rail.BorderSizePixel = 0
        rail.ZIndex = 3
        rail.Parent = progressButton

        local railCorner = Instance.new('UICorner')
        railCorner.CornerRadius = UDim.new(1, 0)
        railCorner.Parent = rail

        local fill = Instance.new('Frame')
        fill.Name = 'Fill'
        fill.AnchorPoint = Vector2.new(0, 0.5)
        fill.Position = UDim2.new(0, 0, 0.5, 0)
        fill.Size = UDim2.new(0, 0, 1, 0)
        fill.BackgroundColor3 = ACCENT
        fill.BorderSizePixel = 0
        fill.ZIndex = 3
        fill.Parent = rail

        local fillCorner = Instance.new('UICorner')
        fillCorner.CornerRadius = UDim.new(1, 0)
        fillCorner.Parent = fill

        -- a thin glow makes the played part read as light, not paint
        local fillGlow = Instance.new('UIStroke')
        fillGlow.Color = ACCENT
        fillGlow.Transparency = 0.45
        fillGlow.Thickness = 2
        fillGlow.Parent = fill

        local knob = Instance.new('Frame')
        knob.Name = 'Knob'
        knob.AnchorPoint = Vector2.new(0.5, 0.5)
        knob.Position = UDim2.new(1, 0, 0.5, 0)
        knob.Size = UDim2.fromOffset(8, 8)
        knob.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
        knob.BorderSizePixel = 0
        knob.ZIndex = 4
        knob.Parent = fill

        local knobCorner = Instance.new('UICorner')
        knobCorner.CornerRadius = UDim.new(1, 0)
        knobCorner.Parent = knob

        local elapsedLabel = Instance.new('TextLabel')
        elapsedLabel.Name = 'Elapsed'
        elapsedLabel.BackgroundTransparency = 1
        elapsedLabel.Position = UDim2.fromOffset(PAD, progressTop + 15)
        elapsedLabel.Size = UDim2.fromOffset(44, 11)
        elapsedLabel.Font = Enum.Font.GothamMedium
        elapsedLabel.TextSize = 10
        elapsedLabel.TextColor3 = TEXT_DIM
        elapsedLabel.TextXAlignment = Enum.TextXAlignment.Left
        elapsedLabel.Text = '0:00'
        elapsedLabel.ZIndex = 3
        elapsedLabel.Parent = panel

        local totalLabel = Instance.new('TextLabel')
        totalLabel.Name = 'Total'
        totalLabel.BackgroundTransparency = 1
        totalLabel.AnchorPoint = Vector2.new(1, 0)
        totalLabel.Position = UDim2.new(1, -PAD, 0, progressTop + 15)
        totalLabel.Size = UDim2.fromOffset(44, 11)
        totalLabel.Font = Enum.Font.GothamMedium
        totalLabel.TextSize = 10
        totalLabel.TextColor3 = TEXT_DIM
        totalLabel.TextXAlignment = Enum.TextXAlignment.Right
        totalLabel.Text = '0:00'
        totalLabel.ZIndex = 3
        totalLabel.Parent = panel

        -- transport --------------------------------------------------------
        local transport = Instance.new('Frame')
        transport.Name = 'Transport'
        transport.BackgroundTransparency = 1
        transport.Position = UDim2.fromOffset(PAD, SEARCH_TOP - 8 - TRANSPORT_HEIGHT)
        transport.Size = UDim2.new(1, -PAD * 2, 0, TRANSPORT_HEIGHT)
        transport.ZIndex = 3
        transport.Parent = panel

        local function makeControl(name, text, width, offset, textSize)
            local control = Instance.new('TextButton')
            control.Name = name
            control.AnchorPoint = Vector2.new(0.5, 0.5)
            control.Position = UDim2.new(0.5, offset, 0.5, 0)
            control.Size = UDim2.fromOffset(width, TRANSPORT_HEIGHT - 2)
            control.BackgroundColor3 = ROW_TINT
            control.BackgroundTransparency = 1
            control.BorderSizePixel = 0
            control.Font = Enum.Font.GothamBold
            control.TextSize = textSize or 15
            control.TextColor3 = TEXT_IDLE
            control.Text = text
            control.AutoButtonColor = false
            control.ZIndex = 3
            control.Parent = transport

            local corner = Instance.new('UICorner')
            corner.CornerRadius = UDim.new(0, 9)
            corner.Parent = control

            return control
        end

        local prevControl = makeControl('Prev', '«', 30, -48, 20)
        local playButton = makeControl('Play', '▶', 36, 0, 14)
        local nextControl = makeControl('Next', '»', 30, 48, 20)
        local shuffleControl = makeControl('Shuffle', '↔', 28, 0, 15)
        local loopControl = makeControl('Loop', '∞', 28, 0, 15)

        shuffleControl.AnchorPoint = Vector2.new(1, 0.5)
        shuffleControl.Position = UDim2.new(1, -32, 0.5, 0)
        loopControl.AnchorPoint = Vector2.new(1, 0.5)
        loopControl.Position = UDim2.new(1, 0, 0.5, 0)

        playButton.BackgroundColor3 = ACCENT
        playButton.BackgroundTransparency = 0.8
        playButton.TextColor3 = TEXT_ACTIVE

        -- the pause state is drawn as two bars: 'II' in the bold font reads
        -- like letters rather than an icon
        local pauseBars = Instance.new('Frame')
        pauseBars.Name = 'PauseBars'
        pauseBars.BackgroundTransparency = 1
        pauseBars.Size = UDim2.fromScale(1, 1)
        pauseBars.Visible = false
        pauseBars.ZIndex = playButton.ZIndex + 1
        pauseBars.Parent = playButton

        for barIndex = 1, 2 do
            local bar = Instance.new('Frame')
            bar.Name = 'Bar' .. barIndex
            bar.AnchorPoint = Vector2.new(0.5, 0.5)
            bar.Position = UDim2.new(0.5, barIndex == 1 and -3 or 3, 0.5, 0)
            bar.Size = UDim2.fromOffset(4, 13)
            bar.BackgroundColor3 = TEXT_ACTIVE
            bar.BorderSizePixel = 0
            bar.ZIndex = playButton.ZIndex + 1
            bar.Parent = pauseBars

            local barCorner = Instance.new('UICorner')
            barCorner.CornerRadius = UDim.new(0, 1)
            barCorner.Parent = bar
        end

        local function bindHover(button, baseTransparency, baseColor)
            bind(button.MouseEnter, function()
                TweenService:Create(
                    button,
                    TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                    { BackgroundTransparency = math.max(0, baseTransparency - 0.1) }
                ):Play()
                if baseColor then
                    button.TextColor3 = TEXT_ACTIVE
                end
            end)

            bind(button.MouseLeave, function()
                TweenService:Create(
                    button,
                    TweenInfo.new(0.18, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                    { BackgroundTransparency = baseTransparency }
                ):Play()
                if baseColor then
                    button.TextColor3 = baseColor
                end
            end)
        end

        bindHover(prevControl, 1, TEXT_IDLE)
        bindHover(nextControl, 1, TEXT_IDLE)
        bindHover(playButton, 0.8, TEXT_ACTIVE)
        bindHover(loopControl, 1)
        bindHover(shuffleControl, 1)

        -- search -----------------------------------------------------------
        local search = Instance.new('TextBox')
        search.Name = 'Search'
        search.BackgroundColor3 = Color3.fromRGB(24, 24, 32)
        search.BackgroundTransparency = 0.1
        search.BorderSizePixel = 0
        search.Position = UDim2.fromOffset(PAD, SEARCH_TOP)
        search.Size = UDim2.new(1, -PAD * 2, 0, SEARCH_HEIGHT)
        search.Font = Enum.Font.GothamMedium
        search.TextSize = 12
        search.TextColor3 = Color3.fromRGB(235, 235, 245)
        search.PlaceholderText = 'search songs'
        search.PlaceholderColor3 = Color3.fromRGB(130, 130, 145)
        search.Text = ''
        search.ClearTextOnFocus = false
        search.TextXAlignment = Enum.TextXAlignment.Left
        search.ZIndex = 3
        search.Parent = panel

        local searchCorner = Instance.new('UICorner')
        searchCorner.CornerRadius = UDim.new(0, 9)
        searchCorner.Parent = search

        local searchGlow = Instance.new('UIStroke')
        searchGlow.Color = ACCENT
        searchGlow.Transparency = 1
        searchGlow.Thickness = 1
        searchGlow.Parent = search

        local searchPadding = Instance.new('UIPadding')
        searchPadding.PaddingLeft = UDim.new(0, 10)
        searchPadding.PaddingRight = UDim.new(0, 28)
        searchPadding.Parent = search

        local clearSearch = Instance.new('TextButton')
        clearSearch.Name = 'Clear'
        clearSearch.AnchorPoint = Vector2.new(1, 0.5)
        clearSearch.Position = UDim2.new(1, -4, 0.5, 0)
        clearSearch.Size = UDim2.fromOffset(22, 22)
        clearSearch.BackgroundTransparency = 1
        clearSearch.BorderSizePixel = 0
        clearSearch.Font = Enum.Font.GothamBold
        clearSearch.TextSize = 12
        clearSearch.TextColor3 = TEXT_MUTED
        clearSearch.Text = '×'
        clearSearch.AutoButtonColor = false
        clearSearch.Visible = false
        clearSearch.ZIndex = 4
        clearSearch.Parent = search

        -- list -------------------------------------------------------------
        local list = Instance.new('ScrollingFrame')
        list.Name = 'List'
        list.BackgroundTransparency = 1
        list.BorderSizePixel = 0
        list.Position = UDim2.fromOffset(PAD, LIST_TOP)
        list.Size = UDim2.new(1, -PAD * 2, 0, ROW_HEIGHT)
        list.CanvasSize = UDim2.new(0, 0, 0, 0)
        list.AutomaticCanvasSize = Enum.AutomaticSize.Y
        list.ScrollBarThickness = 3
        list.ScrollBarImageColor3 = ACCENT
        list.ScrollBarImageTransparency = 0.35
        list.ScrollingDirection = Enum.ScrollingDirection.Y
        list.ZIndex = 2
        list.Parent = panel

        local listLayout = Instance.new('UIListLayout')
        listLayout.FillDirection = Enum.FillDirection.Vertical
        listLayout.SortOrder = Enum.SortOrder.LayoutOrder
        listLayout.Padding = UDim.new(0, ROW_GAP)
        listLayout.Parent = list

        local rows = {}

        for index, track in ipairs(music.tracks) do
            local rowFrame = Instance.new('Frame')
            rowFrame.Name = 'Row' .. index
            rowFrame.BackgroundColor3 = ROW_TINT
            rowFrame.BackgroundTransparency = 1
            rowFrame.BorderSizePixel = 0
            rowFrame.Size = UDim2.new(1, 0, 0, ROW_HEIGHT)
            rowFrame.LayoutOrder = index
            rowFrame.ZIndex = 2
            rowFrame.Parent = list

            local rowCorner = Instance.new('UICorner')
            rowCorner.CornerRadius = UDim.new(0, 8)
            rowCorner.Parent = rowFrame

            local activeBar = Instance.new('Frame')
            activeBar.Name = 'ActiveBar'
            activeBar.AnchorPoint = Vector2.new(0, 0.5)
            activeBar.Position = UDim2.new(0, 0, 0.5, 0)
            activeBar.Size = UDim2.fromOffset(3, ROW_HEIGHT - 14)
            activeBar.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
            activeBar.BackgroundTransparency = 0.15
            activeBar.BorderSizePixel = 0
            activeBar.Visible = false
            activeBar.ZIndex = 3
            activeBar.Parent = rowFrame

            local activeCorner = Instance.new('UICorner')
            activeCorner.CornerRadius = UDim.new(1, 0)
            activeCorner.Parent = activeBar

            local rowCover = Instance.new('Frame')
            rowCover.Name = 'Cover'
            rowCover.Position = UDim2.fromOffset(8, 6)
            rowCover.Size = UDim2.fromOffset(22, 22)
            rowCover.BackgroundColor3 = Color3.fromRGB(60, 60, 72)
            rowCover.BorderSizePixel = 0
            rowCover.ZIndex = 3
            rowCover.Parent = rowFrame

            local rowCoverCorner = Instance.new('UICorner')
            rowCoverCorner.CornerRadius = UDim.new(0, 7)
            rowCoverCorner.Parent = rowCover

            local rowCoverGradient = Instance.new('UIGradient')
            rowCoverGradient.Rotation = 135
            local coverA, coverB = coverColors(index)
            rowCover.BackgroundColor3 = coverA
            rowCoverGradient.Color = ColorSequence.new(coverA, coverB)
            rowCoverGradient.Parent = rowCover

            local rowCoverLabel = Instance.new('TextLabel')
            rowCoverLabel.Name = 'Number'
            rowCoverLabel.BackgroundTransparency = 1
            rowCoverLabel.Size = UDim2.fromScale(1, 1)
            rowCoverLabel.Font = Enum.Font.GothamBold
            rowCoverLabel.TextSize = 9
            rowCoverLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
            rowCoverLabel.Text = string.format('%02d', index)
            rowCoverLabel.ZIndex = 4
            rowCoverLabel.Parent = rowCover

            -- tiny equalizer drawn over the number while this row plays
            local eqBars = {}
            for barIndex = 1, 3 do
                local bar = Instance.new('Frame')
                bar.Name = 'Eq' .. barIndex
                bar.AnchorPoint = Vector2.new(0.5, 1)
                bar.Position = UDim2.fromOffset(11 + (barIndex - 2) * 5, 17)
                bar.Size = UDim2.fromOffset(2, 6)
                bar.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
                bar.BorderSizePixel = 0
                bar.Visible = false
                bar.ZIndex = 5
                bar.Parent = rowCover

                local barCorner = Instance.new('UICorner')
                barCorner.CornerRadius = UDim.new(1, 0)
                barCorner.Parent = bar

                eqBars[barIndex] = bar
            end

            local button = Instance.new('TextButton')
            button.Name = 'Track' .. index
            button.BackgroundTransparency = 1
            button.BorderSizePixel = 0
            button.Size = UDim2.new(1, -34, 1, 0)
            button.Font = Enum.Font.GothamMedium
            button.TextSize = 12
            button.TextColor3 = TEXT_IDLE
            button.TextXAlignment = Enum.TextXAlignment.Left
            button.Text = track.title
            button.TextTruncate = Enum.TextTruncate.AtEnd
            button.AutoButtonColor = false
            button.ZIndex = 2
            button.Parent = rowFrame

            local rowPadding = Instance.new('UIPadding')
            rowPadding.PaddingLeft = UDim.new(0, 38)
            rowPadding.PaddingRight = UDim.new(0, 32)
            rowPadding.Parent = button

            local durationLabel = Instance.new('TextLabel')
            durationLabel.Name = 'Duration'
            durationLabel.AnchorPoint = Vector2.new(1, 0.5)
            durationLabel.Position = UDim2.new(1, -32, 0.5, 0)
            durationLabel.Size = UDim2.fromOffset(34, 12)
            durationLabel.BackgroundTransparency = 1
            durationLabel.Font = Enum.Font.GothamMedium
            durationLabel.TextSize = 9
            durationLabel.TextColor3 = TEXT_DIM
            durationLabel.TextXAlignment = Enum.TextXAlignment.Right
            durationLabel.Text = track.duration and formatTime(track.duration) or ''
            durationLabel.ZIndex = 3
            durationLabel.Parent = rowFrame

            local loopButton = Instance.new('TextButton')
            loopButton.Name = 'Loop' .. index
            loopButton.AnchorPoint = Vector2.new(1, 0.5)
            loopButton.Position = UDim2.new(1, -3, 0.5, 0)
            loopButton.Size = UDim2.fromOffset(24, 22)
            loopButton.BackgroundColor3 = ACCENT
            loopButton.BackgroundTransparency = 1
            loopButton.BorderSizePixel = 0
            loopButton.Font = Enum.Font.GothamBold
            loopButton.TextSize = 13
            loopButton.TextColor3 = TEXT_DIM
            loopButton.Text = '∞'
            loopButton.AutoButtonColor = false
            loopButton.ZIndex = 3
            loopButton.Parent = rowFrame

            local loopCorner = Instance.new('UICorner')
            loopCorner.CornerRadius = UDim.new(0, 7)
            loopCorner.Parent = loopButton

            local hoverTween

            local row = {
                frame = rowFrame,
                button = button,
                duration = durationLabel,
                loopButton = loopButton,
                activeBar = activeBar,
                coverLabel = rowCoverLabel,
                eq = eqBars,
                title = track.title,
                lower = track.title:lower(),
            }

            local function hover(on)
                if music.current == index then
                    return
                end

                if hoverTween then
                    hoverTween:Cancel()
                end

                local target = on and 0.9 or (selected == index and 0.92 or 1)
                hoverTween = TweenService:Create(
                    rowFrame,
                    TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                    { BackgroundTransparency = target }
                )
                hoverTween:Play()

                row.hoverTween = hoverTween
            end

            bind(button.MouseEnter, function()
                hover(true)
            end)

            bind(button.MouseLeave, function()
                hover(false)
            end)

            bind(loopButton.MouseEnter, function()
                hover(true)
            end)

            bind(loopButton.MouseLeave, function()
                hover(false)
            end)

            bind(button.Activated, function()
                selected = index
                loadAndPlay(index)
            end)

            bind(loopButton.Activated, function()
                music.toggleLoop(index)
            end)

            rows[index] = row
        end

        local emptyLabel = Instance.new('TextLabel')
        emptyLabel.Name = 'NoMatches'
        emptyLabel.BackgroundTransparency = 1
        emptyLabel.Size = UDim2.new(1, 0, 0, ROW_HEIGHT)
        emptyLabel.Font = Enum.Font.GothamMedium
        emptyLabel.TextSize = 12
        emptyLabel.TextColor3 = TEXT_MUTED
        emptyLabel.Text = 'no matching song'
        emptyLabel.TextXAlignment = Enum.TextXAlignment.Center
        emptyLabel.LayoutOrder = 100
        emptyLabel.Visible = false
        emptyLabel.ZIndex = 2
        emptyLabel.Parent = list

        -- volume -----------------------------------------------------------
        local footer = Instance.new('Frame')
        footer.Name = 'Footer'
        footer.AnchorPoint = Vector2.new(0, 1)
        footer.Position = UDim2.new(0, PAD, 1, -PAD)
        footer.Size = UDim2.new(1, -PAD * 2, 0, FOOTER_HEIGHT)
        footer.BackgroundTransparency = 1
        footer.ZIndex = 3
        footer.Parent = panel

        local volumeLabel = Instance.new('TextButton')
        volumeLabel.Name = 'VolumeLabel'
        volumeLabel.BackgroundTransparency = 1
        volumeLabel.BorderSizePixel = 0
        volumeLabel.Position = UDim2.fromOffset(0, 0)
        volumeLabel.Size = UDim2.fromOffset(24, FOOTER_HEIGHT)
        volumeLabel.Text = ''
        volumeLabel.AutoButtonColor = false
        volumeLabel.ZIndex = 3
        volumeLabel.Parent = footer

        -- a tiny level meter instead of the word "VOL": three bars that light
        -- up with the volume and a slash across them while muted
        local volumeBars = {}
        for barIndex = 1, 3 do
            local bar = Instance.new('Frame')
            bar.Name = 'Bar' .. barIndex
            bar.AnchorPoint = Vector2.new(0, 1)
            bar.Position = UDim2.fromOffset(2 + (barIndex - 1) * 5, FOOTER_HEIGHT / 2 + 5)
            bar.Size = UDim2.fromOffset(3, 3 + (barIndex - 1) * 4)
            bar.BackgroundColor3 = TEXT_DIM
            bar.BorderSizePixel = 0
            bar.ZIndex = 3
            bar.Parent = volumeLabel

            local barCorner = Instance.new('UICorner')
            barCorner.CornerRadius = UDim.new(0, 1)
            barCorner.Parent = bar

            volumeBars[barIndex] = bar
        end

        local volumeSlash = Instance.new('Frame')
        volumeSlash.Name = 'Slash'
        volumeSlash.AnchorPoint = Vector2.new(0.5, 0.5)
        volumeSlash.Position = UDim2.fromOffset(12, FOOTER_HEIGHT / 2)
        volumeSlash.Size = UDim2.fromOffset(22, 2)
        volumeSlash.Rotation = -45
        volumeSlash.BackgroundColor3 = ACCENT
        volumeSlash.BorderSizePixel = 0
        volumeSlash.Visible = false
        volumeSlash.ZIndex = 4
        volumeSlash.Parent = volumeLabel

        local volumeButton = Instance.new('TextButton')
        volumeButton.Name = 'Volume'
        volumeButton.BackgroundTransparency = 1
        volumeButton.BorderSizePixel = 0
        volumeButton.Position = UDim2.fromOffset(28, 0)
        volumeButton.Size = UDim2.new(1, -28 - 32, 0, FOOTER_HEIGHT)
        volumeButton.Text = ''
        volumeButton.AutoButtonColor = false
        volumeButton.ZIndex = 3
        volumeButton.Parent = footer

        local volumeRail = Instance.new('Frame')
        volumeRail.Name = 'Rail'
        volumeRail.AnchorPoint = Vector2.new(0, 0.5)
        volumeRail.Position = UDim2.new(0, 0, 0.5, 0)
        volumeRail.Size = UDim2.new(1, 0, 0, 3)
        volumeRail.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
        volumeRail.BackgroundTransparency = 0.88
        volumeRail.BorderSizePixel = 0
        volumeRail.ZIndex = 3
        volumeRail.Parent = volumeButton

        local volumeRailCorner = Instance.new('UICorner')
        volumeRailCorner.CornerRadius = UDim.new(1, 0)
        volumeRailCorner.Parent = volumeRail

        local volumeFill = Instance.new('Frame')
        volumeFill.Name = 'Fill'
        volumeFill.AnchorPoint = Vector2.new(0, 0.5)
        volumeFill.Position = UDim2.new(0, 0, 0.5, 0)
        volumeFill.Size = UDim2.new(0, 0, 1, 0)
        volumeFill.BackgroundColor3 = ACCENT
        volumeFill.BorderSizePixel = 0
        volumeFill.ZIndex = 3
        volumeFill.Parent = volumeRail

        local volumeFillCorner = Instance.new('UICorner')
        volumeFillCorner.CornerRadius = UDim.new(1, 0)
        volumeFillCorner.Parent = volumeFill

        local volumePercent = Instance.new('TextLabel')
        volumePercent.Name = 'Percent'
        volumePercent.AnchorPoint = Vector2.new(1, 0)
        volumePercent.Position = UDim2.new(1, 0, 0, 0)
        volumePercent.Size = UDim2.fromOffset(28, FOOTER_HEIGHT)
        volumePercent.BackgroundTransparency = 1
        volumePercent.Font = Enum.Font.GothamMedium
        volumePercent.TextSize = 9
        volumePercent.TextColor3 = TEXT_DIM
        volumePercent.TextXAlignment = Enum.TextXAlignment.Right
        volumePercent.Text = '25%'
        volumePercent.ZIndex = 3
        volumePercent.Parent = footer

        -- click feedback ---------------------------------------------------
        --   one shared ripple, so every control answers a press the same way
        local function pressFX(button)
            button.ClipsDescendants = true

            local ripple = Instance.new('Frame')
            ripple.Name = 'PressRipple'
            ripple.AnchorPoint = Vector2.new(0.5, 0.5)
            ripple.Position = UDim2.fromScale(0.5, 0.5)
            ripple.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
            ripple.BackgroundTransparency = 1
            ripple.BorderSizePixel = 0
            ripple.Size = UDim2.fromOffset(8, 8)
            ripple.ZIndex = math.max(0, button.ZIndex - 1)
            ripple.Parent = button

            local rippleCorner = Instance.new('UICorner')
            rippleCorner.CornerRadius = UDim.new(1, 0)
            rippleCorner.Parent = ripple

            bind(button.Activated, function()
                local width = math.max(button.AbsoluteSize.X, button.AbsoluteSize.Y)
                local size = math.max(14, width * 1.7)

                ripple.Size = UDim2.fromOffset(8, 8)
                ripple.BackgroundTransparency = 0.8

                TweenService:Create(
                    ripple,
                    TweenInfo.new(0.3, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                    { Size = UDim2.fromOffset(size, size), BackgroundTransparency = 1 }
                ):Play()
            end)
        end

        pressFX(prevControl)
        pressFX(playButton)
        pressFX(nextControl)
        pressFX(shuffleControl)
        pressFX(loopControl)
        pressFX(closeButton)
        pressFX(clearSearch)
        pressFX(volumeLabel)

        for _, row in ipairs(rows) do
            pressFX(row.button)
            pressFX(row.loopButton)
        end

        -- the seek bar knob grows under the pointer
        bind(progressButton.MouseEnter, function()
            TweenService:Create(
                knob,
                TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                { Size = UDim2.fromOffset(11, 11) }
            ):Play()
        end)

        bind(progressButton.MouseLeave, function()
            TweenService:Create(
                knob,
                TweenInfo.new(0.18, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                { Size = UDim2.fromOffset(8, 8) }
            ):Play()
        end)

        -- helpers ----------------------------------------------------------
        local function fractionAt(button, positionX)
            local origin = button.AbsolutePosition
            local width = math.max(1, button.AbsoluteSize.X)
            return math.clamp((positionX - origin.X) / width, 0, 1)
        end

        local function visibleRowCount()
            local count = 0

            for _, row in ipairs(rows) do
                if row.frame.Visible then
                    count += 1
                end
            end

            return math.max(1, count)
        end

        local function targetPanelHeight()
            local count = visibleRowCount()
            return CHROME + count * ROW_HEIGHT + (count - 1) * ROW_GAP
        end

        local function panelMetrics()
            local origin = root.AbsolutePosition
            local space = root.AbsoluteSize
            local guiWidth, guiHeight = space.X, space.Y

            if guiWidth < 40 or guiHeight < 40 then
                local camera = workspace.CurrentCamera
                local viewport = camera and camera.ViewportSize or Vector2.new(1280, 720)
                guiWidth, guiHeight = viewport.X, viewport.Y
            end

            local islandPos = island.AbsolutePosition
            local islandSize = island.AbsoluteSize
            local islandX = islandPos.X - origin.X
            local islandY = islandPos.Y - origin.Y
            local islandW = math.max(1, islandSize.X)
            local islandH = math.max(1, islandSize.Y)

            local gap = 8
            local content = targetPanelHeight()
            local belowTop = islandY + islandH + gap
            local aboveBottom = islandY - gap
            local spaceBelow = guiHeight - gap - belowTop
            local spaceAbove = aboveBottom - gap
            local minimum = CHROME + (ROW_HEIGHT + ROW_GAP) * 3

            local below
            if spaceBelow >= minimum and spaceAbove >= minimum then
                below = spaceBelow >= spaceAbove
            elseif spaceBelow >= minimum then
                below = true
            elseif spaceAbove >= minimum then
                below = false
            else
                below = spaceBelow >= spaceAbove
            end

            panelBelow = below

            -- the card is never taller than the side it opens towards, so it
            -- can never slide back over (or under) the island.  When that side
            -- is very short the card just gets shorter and the list scrolls.
            local room = below and spaceBelow or spaceAbove
            local height = math.min(content, math.max(ROW_HEIGHT, room))

            local x = islandX + islandW / 2
            local minX = PANEL_WIDTH / 2 + gap
            x = math.clamp(x, minX, math.max(minX, guiWidth - PANEL_WIDTH / 2 - gap))

            -- pin the edge that faces the island and let the other one fall
            -- wherever the height puts it, so the gap to the island is exact
            local y = below and belowTop or aboveBottom

            local listHeight = math.max(ROW_HEIGHT, height - CHROME)
            return x, y, height, listHeight
        end

        local function positionPanel()
            local x, y, height, listHeight = panelMetrics()

            -- anchor the edge that faces the island, so the card opens and
            -- collapses towards the island instead of drifting away from it
            panel.AnchorPoint = panelBelow and Vector2.new(0.5, 0) or Vector2.new(0.5, 1)
            panel.Position = UDim2.fromOffset(x, y)
            list.Size = UDim2.new(1, -PAD * 2, 0, listHeight)
            return height
        end

        local function positionDroplet()
            local origin = root.AbsolutePosition
            local islandPos = island.AbsolutePosition
            local islandSize = island.AbsoluteSize
            local x = islandPos.X - origin.X + islandSize.X / 2
            local top = islandPos.Y - origin.Y

            if panelBelow then
                droplet.AnchorPoint = Vector2.new(0.5, 0)
                droplet.Position = UDim2.fromOffset(x, top + islandSize.Y + 1)
            else
                droplet.AnchorPoint = Vector2.new(0.5, 1)
                droplet.Position = UDim2.fromOffset(x, top - 1)
            end
        end

        applyRowStyle = function(index)
            local row = rows[index]
            if not row then
                return
            end

            local active = music.current == index
            local isSelected = selected == index

            if row.hoverTween then
                row.hoverTween:Cancel()
                row.hoverTween = nil
            end

            row.frame.BackgroundColor3 = active and ACCENT or ROW_TINT
            row.frame.BackgroundTransparency = active and 0.82 or (isSelected and 0.92 or 1)
            row.button.TextColor3 = active and TEXT_ACTIVE
                or (isSelected and TEXT_ACTIVE or TEXT_IDLE)
            row.button.Font = active and Enum.Font.GothamBold or Enum.Font.GothamMedium
            row.activeBar.Visible = active

            local looped = music.isLooped(index)
            row.loopButton.TextColor3 = looped
                and (active and TEXT_ACTIVE or ACCENT)
                or TEXT_DIM
            row.loopButton.BackgroundTransparency = looped and 0.74 or 1
        end

        refreshRows = function()
            for index, row in ipairs(rows) do
                applyRowStyle(index)

                local length = music.length(index)
                row.duration.Text = length > 0 and formatTime(length) or ''
            end
        end

        animateRows = function()
            eqPhase += 0.55
            local playing = music.isPlaying()

            for index, row in ipairs(rows) do
                local active = music.current == index and playing
                row.coverLabel.Visible = not active

                if active then
                    -- the marker breathes with the equalizer
                    row.activeBar.BackgroundTransparency =
                        0.15 + 0.35 * (0.5 + 0.5 * math.sin(eqPhase * 0.5))
                end

                for barIndex, bar in ipairs(row.eq) do
                    bar.Visible = active

                    if active then
                        local height = 4 + 11 * (0.5 + 0.5 * math.sin(eqPhase + barIndex * 1.15))
                        bar.Size = UDim2.fromOffset(2, height)
                    end
                end
            end
        end

        updateHeader = function()
            local index = music.current
            local displayIndex = loadingIndex or index
            local track = displayIndex and music.tracks[displayIndex] or nil
            local playing = music.isPlaying()

            if track then
                local total = music.length(displayIndex)
                local mode

                if loadingIndex then
                    mode = 'loading'
                elseif failedTitle and not playing then
                    mode = 'could not load ' .. failedTitle
                elseif playing then
                    mode = 'now playing'
                else
                    mode = 'paused'
                end

                titleLabel.Text = track.title
                coverNumber.Text = string.format('%02d', displayIndex)

                local colorA, colorB = coverColors(displayIndex)
                cover.BackgroundColor3 = colorA
                coverGradient.Color = ColorSequence.new(colorA, colorB)

                statusLabel.Text = total > 0
                    and string.format('%s  ·  %s', mode, formatTime(total))
                    or mode
                statusLabel.TextColor3 = (failedTitle and not playing)
                    and DANGER
                    or TEXT_MUTED
            else
                titleLabel.Text = 'Music'
                coverNumber.Text = '--'
                cover.BackgroundColor3 = ACCENT
                coverGradient.Color = ColorSequence.new(
                    ACCENT,
                    ACCENT:Lerp(Color3.new(0, 0, 0), 0.5)
                )

                if loadingIndex and music.tracks[loadingIndex] then
                    statusLabel.Text = 'loading · ' .. music.tracks[loadingIndex].title
                    statusLabel.TextColor3 = TEXT_MUTED
                elseif failedTitle then
                    statusLabel.Text = 'could not load ' .. failedTitle
                    statusLabel.TextColor3 = DANGER
                else
                    statusLabel.Text = 'choose a song'
                    statusLabel.TextColor3 = TEXT_MUTED
                end
            end

            local loopIndex = index or selected
            local looped = loopIndex ~= nil and music.isLooped(loopIndex)

            loopControl.TextColor3 = looped and ACCENT or TEXT_IDLE
            shuffleControl.TextColor3 = music.shuffle and ACCENT or TEXT_IDLE
            playButton.Text = playing and '' or '▶'
            pauseBars.Visible = playing
        end

        updateProgress = function()
            -- while the bar is being dragged the fill follows the mouse, not
            -- the sound, so it does not fight the preview
            if scrubbing then
                return
            end

            local total = music.length(music.current)
            local position = math.clamp(music.position(), 0, math.max(0, total))
            local fraction = total > 0 and (position / total) or 0

            fill.Size = UDim2.new(fraction, 0, 1, 0)
            elapsedLabel.Text = formatTime(position)
            totalLabel.Text = total > 0 and formatTime(total) or '0:00'
        end

        updateVolume = function()
            local value = math.clamp(music.volume or 0, 0, 1)
            local muted = music.muted == true
            local lit = math.ceil(value * 3)

            volumeFill.Size = UDim2.new(muted and 0 or value, 0, 1, 0)
            volumeSlash.Visible = muted

            for barIndex, bar in ipairs(volumeBars) do
                local on = not muted and barIndex <= lit
                bar.BackgroundColor3 = on and ACCENT or TEXT_DIM
                bar.BackgroundTransparency = on and 0 or 0.45
            end

            if muted then
                volumePercent.Text = 'MUTE'
                volumePercent.TextColor3 = ACCENT
            else
                volumePercent.Text = string.format('%d%%', math.floor(value * 100 + 0.5))
                volumePercent.TextColor3 = TEXT_DIM
            end
        end

        local lastSignature = nil

        local function currentSignature()
            local bits = {
                tostring(music.current or 0),
                tostring(selected or 0),
                tostring(loadingIndex or 0),
                tostring(music.muted == true),
                tostring(music.shuffle == true),
                tostring(failedTitle or ''),
            }

            for index = 1, #music.tracks do
                bits[#bits + 1] = music.isLooped(index) and '1' or '0'
            end

            return table.concat(bits, '|')
        end

        -- the card repaints itself from a Heartbeat tick, so its controls stay
        -- live even when a change callback is missed.  It deliberately does not
        -- depend on panelOpen: while the card is hidden this is a few cheap
        -- assignments, and it can never get stuck showing stale state.
        syncUI = function(force)
            local signature = currentSignature()
            if force or signature ~= lastSignature then
                lastSignature = signature
                refreshRows()
            end

            updateHeader()
            updateProgress()
            updateVolume()
            animateRows()
        end

        music.onChange = function()
            if music.current and music.isPlaying() then
                failedTitle = nil
            end

            -- force a full repaint: a change that arrives here has to be
            -- visible right away, not on the next tick
            syncUI(true)
        end

        -- drive the card from Heartbeat, the same signal the FPS meter uses.
        -- It is connected here, before any of the interaction wiring, so the
        -- card keeps repainting even if a later step of this build fails.
        local tickAccum = 0
        local tickWarned = false

        bind(RunService.Heartbeat, function(dt)
            tickAccum += dt

            if tickAccum < 0.1 then
                return
            end

            tickAccum = 0

            local ok, err = pcall(syncUI)

            if not ok and not tickWarned then
                tickWarned = true
                warn('[' .. BRAND .. '] picker refresh failed: ' .. tostring(err))

                -- tell the user instead of silently freezing the card
                pcall(function()
                    statusLabel.Text = 'refresh error - see console'
                    statusLabel.TextColor3 = DANGER
                end)
            end
        end)

        local function resizePanel()
            if not panelOpen then
                return
            end

            -- positionPanel re-anchors instantly so the edge nearest the
            -- island stays pinned while only the size is animated
            local height = positionPanel()

            if panelTween then
                panelTween:Cancel()
            end

            panelTween = TweenService:Create(
                panel,
                TweenInfo.new(0.2, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                { Size = UDim2.fromOffset(PANEL_WIDTH, height) }
            )
            panelTween:Play()
        end

        closePanel = function()
            if not panelOpen then
                return
            end
            panelOpen = false

            overlay.Visible = false
            dropletToken += 1
            droplet.Visible = false

            if search:IsFocused() then
                search:ReleaseFocus()
            end

            if panelTween then
                panelTween:Cancel()
            end

            panelTween = TweenService:Create(
                panel,
                TweenInfo.new(0.2, Enum.EasingStyle.Quad, Enum.EasingDirection.In),
                { Size = UDim2.fromOffset(PANEL_WIDTH, 0) }
            )
            panelTween:Play()

            panelTween.Completed:Once(function()
                if not panelOpen then
                    panel.Visible = false
                end
            end)
        end

        local function openPanel()
            if panelOpen then
                return
            end
            panelOpen = true

            overlay.Visible = true
            panel.Visible = true
            panelCorner.CornerRadius = UDim.new(1, 0)

            selected = music.current or selected or 1
            lastSignature = nil
            syncUI(true)

            -- the cover snaps upright with a little overshoot
            cover.Rotation = -9
            TweenService:Create(
                cover,
                TweenInfo.new(0.45, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
                { Rotation = 0 }
            ):Play()

            local height = positionPanel()
            panel.Size = UDim2.fromOffset(PANEL_WIDTH, 0)

            -- bloom from the edge nearest the island
            ripple.AnchorPoint = panelBelow and Vector2.new(0.5, 0) or Vector2.new(0.5, 1)
            ripple.Position = panelBelow and UDim2.new(0.5, 0, 0, 0) or UDim2.new(0.5, 0, 1, 0)
            ripple.Size = UDim2.fromOffset(40, 40)
            ripple.BackgroundTransparency = 0.4

            TweenService:Create(
                ripple,
                TweenInfo.new(0.6, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                {
                    Size = UDim2.fromOffset(PANEL_WIDTH * 2, PANEL_WIDTH * 2),
                    BackgroundTransparency = 1,
                }
            ):Play()

            -- glass droplet: drips from the island and melts into the card
            positionDroplet()
            dropletToken += 1
            local token = dropletToken
            local direction = panelBelow and 1 or -1

            droplet.Visible = true
            droplet.Size = UDim2.fromOffset(10, 10)
            droplet.BackgroundTransparency = 0.25
            dropletStroke.Transparency = 0.35

            TweenService:Create(
                droplet,
                TweenInfo.new(0.16, Enum.EasingStyle.Quad, Enum.EasingDirection.In),
                {
                    Size = UDim2.fromOffset(14, 22),
                    Position = UDim2.fromOffset(
                        droplet.Position.X.Offset,
                        droplet.Position.Y.Offset + 10 * direction
                    ),
                }
            ):Play()

            task.delay(0.16, function()
                if token ~= dropletToken then
                    return
                end

                TweenService:Create(
                    droplet,
                    TweenInfo.new(0.34, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                    {
                        Size = UDim2.fromOffset(PANEL_WIDTH * 0.92, 30),
                        BackgroundTransparency = 1,
                    }
                ):Play()

                TweenService:Create(
                    dropletStroke,
                    TweenInfo.new(0.34, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                    { Transparency = 1 }
                ):Play()

                task.delay(0.36, function()
                    if token == dropletToken then
                        droplet.Visible = false
                    end
                end)
            end)

            TweenService:Create(
                panelCorner,
                TweenInfo.new(0.5, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                { CornerRadius = UDim.new(0, 16) }
            ):Play()

            if panelTween then
                panelTween:Cancel()
            end

            panelTween = TweenService:Create(
                panel,
                TweenInfo.new(0.36, Enum.EasingStyle.Quint, Enum.EasingDirection.Out),
                { Size = UDim2.fromOffset(PANEL_WIDTH, height) }
            )
            panelTween:Play()

            task.defer(scrollToSelected)
        end

        local lastToggleAt = -1

        local function openOrClosePanel()
            -- the same click must never toggle twice (mouse + synthetic
            -- touch, or a release that arrives twice)
            if os.clock() - lastToggleAt < 0.12 then
                return
            end

            lastToggleAt = os.clock()

            if panelOpen then
                closePanel()
            else
                openPanel()
            end
        end

        -- hand the real implementations to the island
        togglePanel = openOrClosePanel
        syncPanel = function()
            if not panelOpen then
                return
            end

            local height = positionPanel()

            if panelTween then
                panelTween:Cancel()
            end

            panel.Size = UDim2.fromOffset(PANEL_WIDTH, height)
        end

        loadAndPlay = function(index)
            if not music.tracks[index] then
                return
            end

            loadingIndex = index
            failedTitle = nil
            selected = index

            syncUI(true)

            task.spawn(function()
                task.wait(0.05)

                local okCall, okPlay = pcall(music.play, index)

                if not okCall or not okPlay then
                    failedTitle = music.tracks[index].title
                end

                loadingIndex = nil
                syncUI(true)
            end)
        end

        scrollToSelected = function()
            local offset = 0

            for index, row in ipairs(rows) do
                if row.frame.Visible then
                    if index == selected then
                        break
                    end
                    offset += ROW_HEIGHT + ROW_GAP
                end
            end

            local view = list.AbsoluteSize.Y
            local canvas = 0

            local okSize, size = pcall(function()
                return list.AbsoluteCanvasSize
            end)

            if okSize and typeof(size) == 'Vector2' then
                canvas = size.Y
            else
                canvas = list.CanvasSize.Y.Offset
            end

            local target = math.clamp(
                offset - (view - ROW_HEIGHT) / 2,
                0,
                math.max(0, canvas - view)
            )

            list.CanvasPosition = Vector2.new(0, target)
        end

        local function moveSelection(delta)
            local visible = {}

            for index, row in ipairs(rows) do
                if row.frame.Visible then
                    table.insert(visible, index)
                end
            end

            if #visible == 0 then
                return
            end

            local position = table.find(visible, selected) or 1
            position = ((position - 1 + delta) % #visible) + 1
            selected = visible[position]

            refreshRows()
            scrollToSelected()
        end

        local function applyFilter()
            local query = search.Text:lower()
            query = query:gsub('^%s+', ''):gsub('%s+$', '')

            local matches = 0
            local firstMatch = nil

            for index, row in ipairs(rows) do
                local match = query == '' or row.lower:find(query, 1, true) ~= nil
                row.frame.Visible = match

                if match then
                    matches += 1
                    firstMatch = firstMatch or index
                end
            end

            emptyLabel.Visible = matches == 0
            clearSearch.Visible = search.Text ~= ''

            if matches > 0 and (not rows[selected] or not rows[selected].frame.Visible) then
                selected = firstMatch
            end

            refreshRows()
            resizePanel()
            task.defer(scrollToSelected)
        end

        -- interactions -----------------------------------------------------
        local function previewScrub(positionX)
            local total = music.length(music.current)
            if total <= 0 then
                return
            end

            scrubFraction = fractionAt(progressButton, positionX)
            fill.Size = UDim2.new(scrubFraction, 0, 1, 0)
            elapsedLabel.Text = formatTime(total * scrubFraction)
        end

        local function commitScrub()
            local total = music.length(music.current)

            if total > 0 and scrubFraction then
                music.seek(total * scrubFraction)
            end
        end

        bind(progressButton.InputBegan, function(input)
            if not isPrimary(input) then
                return
            end

            -- a click jumps straight away; a drag previews and commits on
            -- release, so the audio does not stutter while scrubbing
            scrubbing = true
            previewScrub(input.Position.X)
            commitScrub()
            syncUI(true)
        end)

        bind(volumeButton.InputBegan, function(input)
            if not isPrimary(input) then
                return
            end

            volumeDragging = true
            music.setVolume(fractionAt(volumeButton, input.Position.X))
        end)

        bind(UserInputService.InputChanged, function(input)
            if input.UserInputType ~= Enum.UserInputType.MouseMovement
                and input.UserInputType ~= Enum.UserInputType.Touch then
                return
            end

            if scrubbing then
                previewScrub(input.Position.X)
            end

            if volumeDragging then
                music.setVolume(fractionAt(volumeButton, input.Position.X))
            end
        end)

        bind(UserInputService.InputEnded, function(input)
            if not isPrimary(input) then
                return
            end

            if scrubbing then
                commitScrub()
            end

            scrubbing = false
            scrubFraction = nil
            volumeDragging = false
        end)

        -- every control repaints the card itself as well as relying on the
        -- engine callback, so a click is always visible immediately
        bind(prevControl.Activated, function()
            music.step(-1)
            syncUI(true)
        end)

        bind(nextControl.Activated, function()
            music.step(1)
            syncUI(true)
        end)

        bind(playButton.Activated, function()
            music.toggle()
            syncUI(true)
        end)

        bind(loopControl.Activated, function()
            local index = music.current or selected
            if index then
                music.toggleLoop(index)
            end
            syncUI(true)
        end)

        bind(shuffleControl.Activated, function()
            music.toggleShuffle()
            syncUI(true)
        end)

        bind(volumeLabel.Activated, function()
            music.toggleMute()
            syncUI(true)
        end)

        bind(clearSearch.Activated, function()
            search.Text = ''
        end)

        bind(closeButton.Activated, closePanel)
        bind(overlay.Activated, closePanel)

        search.TextChanged:Connect(applyFilter)

        -- the search field lights up while it has focus
        bind(search.Focused, function()
            TweenService:Create(
                searchGlow,
                TweenInfo.new(0.18, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                { Transparency = 0.35 }
            ):Play()
        end)

        bind(search.FocusLost, function()
            TweenService:Create(
                searchGlow,
                TweenInfo.new(0.22, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
                { Transparency = 1 }
            ):Play()
        end)

        search.FocusLost:Connect(function(enterPressed)
            if enterPressed and rows[selected] and rows[selected].frame.Visible then
                loadAndPlay(selected)
            end
        end)

        bind(UserInputService.InputBegan, function(input, processed)
            if processed or not panelOpen then
                return
            end
            if UserInputService:GetFocusedTextBox() then
                return
            end

            local key = input.KeyCode

            if key == Enum.KeyCode.Escape then
                closePanel()
            elseif key == Enum.KeyCode.Slash then
                search:CaptureFocus()
                task.defer(function()
                    if search.Text == '/' then
                        search.Text = ''
                    end
                end)
            elseif key == Enum.KeyCode.Down then
                moveSelection(1)
            elseif key == Enum.KeyCode.Up then
                moveSelection(-1)
            elseif key == Enum.KeyCode.Left then
                music.seekBy(-5)
            elseif key == Enum.KeyCode.Right then
                music.seekBy(5)
            elseif key == Enum.KeyCode.M then
                music.toggleMute()
            elseif key == Enum.KeyCode.L then
                local index = music.current or selected
                if index then
                    music.toggleLoop(index)
                end
            elseif key == Enum.KeyCode.Return or key == Enum.KeyCode.KeypadEnter then
                if selected then
                    loadAndPlay(selected)
                end
            elseif key == Enum.KeyCode.Space then
                music.toggle()
            end
        end)

        -- initial paint
        refreshRows()

        screenGui.Destroying:Connect(function()
            for _, connection in ipairs(connections) do
                connection:Disconnect()
            end

            if music.onChange then
                music.onChange = nil
            end
        end)
        end)

        if not pickerOk then
            warn('[' .. BRAND .. '] song picker failed to build: ' .. tostring(pickerError))
            music.onChange = nil
        end

        -- wave animation ----------------------------------------------------
        task.spawn(function()
            local phase = 0

            while screenGui.Parent do
                local playing = music.isPlaying()

                waveHolder.Visible = playing

                if playing then
                    phase += 0.42
                    stroke.Transparency = 0.4 + 0.18 * (0.5 + 0.5 * math.sin(phase * 0.85))

                    for index, bar in ipairs(waveBars) do
                        local height = 3 + 9 * (0.5 + 0.5 * math.sin(phase + index * 0.85))
                        bar.Size = UDim2.fromOffset(2, height)
                    end
                else
                    stroke.Transparency = 0.6
                end

                -- now playing indicator
                local current = music.current
                local track = current and music.tracks[current] or nil

                if track then
                    local title = '♪ ' .. track.title

                    if songLabel.Text ~= title then
                        songLabel.Text = title
                        fitIsland()
                    end

                    songLabel.Visible = songAllowed

                    local total = music.length(current)
                    local fraction = 0

                    if total > 0 then
                        fraction = math.clamp(music.position() / total, 0, 1)
                    end

                    local origin = hudRoot.AbsolutePosition
                    local islandPos = island.AbsolutePosition
                    local islandSize = island.AbsoluteSize
                    local left = islandPos.X - origin.X + 10
                    local top = islandPos.Y - origin.Y + islandSize.Y - 4
                    local width = math.max(0, islandSize.X - 20)

                    progressTrack.Position = UDim2.fromOffset(left, top)
                    progressTrack.Size = UDim2.fromOffset(width, 2)
                    progressLine.Position = UDim2.fromOffset(left, top)
                    progressLine.Size = UDim2.fromOffset(width * fraction, 2)

                    local showLine = island.Visible and width > 20
                    progressTrack.Visible = showLine
                    progressLine.Visible = showLine
                elseif songLabel.Visible or progressLine.Visible then
                    songLabel.Visible = false
                    progressTrack.Visible = false
                    progressLine.Visible = false
                    fitIsland()
                end

                task.wait(0.06)
            end
        end)

        -- presence --------------------------------------------------------
        local hasAvatar = false
        local manualStatus = nil
        local lastAvatarId = nil
        local lastDisplay = nil
        local lastStatus = nil
        local lastPlatform = nil

        local function render(display, status, platform)
            local color = STATUS_COLORS[status] or STATUS_COLORS.unknown

            if not hasAvatar then
                avatar.BackgroundColor3 = color
            end
            dot.BackgroundColor3 = color
            stroke.Color = color
            stroke.Transparency = 0.55

            lastDisplay = display
            lastStatus = status
            lastPlatform = platform

            if compactPresence then
                nameLabel.Text = '<font color="' .. colorHex(ACCENT) .. '">'
                    .. escapeRich(BRAND) .. '</font>'
                return
            end

            local text = '<font color="' .. colorHex(ACCENT) .. '">' .. escapeRich(BRAND) .. '</font>  '
                .. escapeRich(display)

            if type(status) == 'string' and status ~= '' and status ~= 'unknown' then
                local word = status
                if status ~= 'offline' and type(platform) == 'string' and platform ~= '' then
                    word = status .. ' (' .. platform .. ')'
                end
                text = text .. '  <font color="' .. colorHex(color) .. '">' .. escapeRich(word) .. '</font>'
            end

            nameLabel.Text = text
        end

        redrawPresence = function()
            if lastDisplay then
                render(lastDisplay, lastStatus, lastPlatform)
            end
        end

        local function setAvatar(asset)
            if asset then
                avatar.Image = asset
                avatar.ImageTransparency = 0
                avatar.BackgroundTransparency = 1
                dot.Visible = true
                hasAvatar = true
            else
                avatar.ImageTransparency = 1
                avatar.BackgroundTransparency = 0
                dot.Visible = false
                hasAvatar = false
            end
        end

        local function refreshPresence()
            if manualStatus then
                render(DISCORD_NAME_OVERRIDE ~= '' and DISCORD_NAME_OVERRIDE or 'you', manualStatus, nil)
                return
            end

            if DISCORD_ID == '' then
                if DISCORD_NAME_OVERRIDE ~= '' then
                    render(DISCORD_NAME_OVERRIDE, 'unknown', nil)
                end
                return
            end

            local body = httpGet(LANYARD .. DISCORD_ID)
            if type(body) ~= 'string' then
                return
            end

            local ok, decoded = pcall(function()
                return HttpService:JSONDecode(body)
            end)
            if not ok or type(decoded) ~= 'table' then
                return
            end

            if decoded.success ~= true or type(decoded.data) ~= 'table' then
                render(DISCORD_NAME_OVERRIDE ~= '' and DISCORD_NAME_OVERRIDE or 'not linked', 'unknown', nil)
                return
            end

            local data = decoded.data
            local user = type(data.discord_user) == 'table' and data.discord_user or {}
            local status = type(data.discord_status) == 'string' and data.discord_status or 'offline'

            local display = DISCORD_NAME_OVERRIDE
            if display == '' then
                display = user.global_name
            end
            if type(display) ~= 'string' or display == '' then
                display = user.username
            end
            if type(display) ~= 'string' or display == '' then
                display = 'unknown'
            end

            local platform = 'desktop'
            if data.active_on_discord_mobile == true then
                platform = 'mobile'
            elseif data.active_on_discord_web == true then
                platform = 'web'
            end

            render(display, status, platform)

            local wantId = tostring(user.id or '')
            if wantId ~= '' and wantId ~= lastAvatarId then
                lastAvatarId = wantId

                local hash = user.avatar
                local url
                if type(hash) == 'string' and hash ~= '' then
                    url = CDN .. 'avatars/' .. wantId .. '/' .. hash .. '.png?size=64'
                else
                    url = CDN .. 'embed/avatars/0.png'
                end

                setAvatar(assetFromUrl(url, 'prampa_avatar_' .. wantId .. '.png'))
            end
        end

        -- dragging + collapse --------------------------------------------
        --   a press only becomes a drag once the pointer really moved, so a
        --   plain click opens the card instead.  Movement is read from three
        --   sources because executors fill them inconsistently: InputObject
        --   Delta, the absolute position, and the polled mouse location.
        local DRAG_THRESHOLD = 5

        local pressInput = nil
        local pressAt = 0
        local lastPointer = Vector2.zero
        local lastPoll = Vector2.zero
        local pollAvailable = false
        local dragSource = nil
        local pressMoved = false
        local dragOrigin = Vector2.zero
        local dragDelta = Vector2.zero
        local dragSpace = Vector2.zero

        local function beginDrag()
            -- absolute screen position -> gui-space offset, without moving
            local origin = hudRoot.AbsolutePosition
            local position = island.AbsolutePosition

            dragOrigin = Vector2.new(position.X - origin.X, position.Y - origin.Y)
            dragSpace = hudRoot.AbsoluteSize

            island.AnchorPoint = Vector2.new(0, 0)
            island.Position = UDim2.fromOffset(dragOrigin.X, dragOrigin.Y)
        end

        local function moveDrag()
            local size = island.AbsoluteSize

            local x = math.clamp(
                dragOrigin.X + dragDelta.X,
                0,
                math.max(0, dragSpace.X - size.X)
            )
            local y = math.clamp(
                dragOrigin.Y + dragDelta.Y,
                0,
                math.max(0, dragSpace.Y - size.Y)
            )

            island.Position = UDim2.fromOffset(x, y)
            syncPanel()
        end

        local function applyMove(dx, dy)
            dragDelta += Vector2.new(dx, dy)

            if not pressMoved then
                if dragDelta.Magnitude < DRAG_THRESHOLD then
                    return
                end

                pressMoved = true
                beginDrag()
            end

            moveDrag()
        end

        -- a press is finished exactly once, whether the end arrives as an
        -- InputEnded, as a state change or from the held-button check
        local function releasePress()
            if not pressInput then
                return
            end

            local wasDrag = pressMoved

            pressInput = nil
            dragSource = nil
            pressMoved = false
            island.BackgroundTransparency = 0.12

            if wasDrag then
                env.UE_ISLAND_POSITION = island.Position
                config.island = {
                    x = island.Position.X.Offset,
                    y = island.Position.Y.Offset,
                }
                queueSave()
            else
                togglePanel()
            end
        end

        island.InputBegan:Connect(function(input)
            if input.UserInputType ~= Enum.UserInputType.MouseButton1
                and input.UserInputType ~= Enum.UserInputType.Touch then
                return
            end

            -- one press at a time: a duplicated event must not toggle twice.
            -- A press that never reported its release is dropped instead of
            -- blocking the island for the rest of the session.
            if pressInput then
                if os.clock() - pressAt < 0.5 then
                    return
                end

                pressInput = nil
                dragSource = nil
                pressMoved = false
                dragDelta = Vector2.zero
            end

            pressAt = os.clock()
            pressInput = input
            lastPointer = Vector2.new(input.Position.X, input.Position.Y)
            pressMoved = false
            dragSource = nil
            dragDelta = Vector2.zero

            island.BackgroundTransparency = 0.04

            local okLocation, location = pcall(function()
                return UserInputService:GetMouseLocation()
            end)

            pollAvailable = okLocation and typeof(location) == 'Vector2'
            lastPoll = pollAvailable and Vector2.new(location.X, location.Y) or lastPointer
        end)

        UserInputService.InputChanged:Connect(function(input)
            if not pressInput or dragSource == 'poll' then
                return
            end

            local isTouch = input.UserInputType == Enum.UserInputType.Touch

            if not isTouch and input.UserInputType ~= Enum.UserInputType.MouseMovement then
                return
            end

            local delta = input.Delta
            if not isTouch and delta and (delta.X ~= 0 or delta.Y ~= 0) then
                dragSource = dragSource or 'delta'
                applyMove(delta.X, delta.Y)
                return
            end

            local position = input.Position
            local nextPointer = Vector2.new(position.X, position.Y)
            local step = nextPointer - lastPointer
            lastPointer = nextPointer

            if step.Magnitude > 0 then
                dragSource = dragSource or 'absolute'
                applyMove(step.X, step.Y)
            end
        end)

        -- fallback for a mouse that reports no Delta and no moving position:
        -- poll the location instead, and let it own the drag once it moves
        RunService.RenderStepped:Connect(function()
            if not pressInput or dragSource or not pollAvailable then
                return
            end

            if pressInput.UserInputType ~= Enum.UserInputType.MouseButton1 then
                return
            end

            local okLocation, location = pcall(function()
                return UserInputService:GetMouseLocation()
            end)

            if not okLocation or typeof(location) ~= 'Vector2' then
                pollAvailable = false
                return
            end

            local now = Vector2.new(location.X, location.Y)
            local step = now - lastPoll
            lastPoll = now

            if step.Magnitude > 0 then
                dragSource = 'poll'
                applyMove(step.X, step.Y)
            end
        end)

        UserInputService.InputEnded:Connect(function(input)
            if not pressInput then
                return
            end

            if input.UserInputType ~= pressInput.UserInputType then
                return
            end

            releasePress()
        end)

        -- if the release is ever swallowed, notice the button is no longer
        -- held rather than leaving the island stuck in drag mode
        RunService.Heartbeat:Connect(function()
            if not pressInput then
                return
            end

            if pressInput.UserInputType ~= Enum.UserInputType.MouseButton1 then
                return
            end

            local okPressed, pressed = pcall(function()
                return UserInputService:IsMouseButtonPressed(Enum.UserInputType.MouseButton1)
            end)

            if okPressed and pressed == false then
                releasePress()
            end
        end)

        -- fps ------------------------------------------------------------
        local fps = 0
        local fpsAccum = 0
        local fpsFrames = 0

        RunService.RenderStepped:Connect(function(dt)
            fpsAccum += dt
            fpsFrames += 1

            if fpsAccum >= 0.25 then
                fps = fpsFrames / fpsAccum
                fpsAccum = 0
                fpsFrames = 0
            end
        end)

        local function fpsColor(value)
            if value >= 120 then
                return Color3.fromRGB(120, 230, 150)
            elseif value >= 60 then
                return Color3.fromRGB(240, 210, 110)
            end
            return Color3.fromRGB(240, 110, 110)
        end

        local function pingColor(value)
            if value <= 0 then
                return Color3.fromRGB(150, 150, 160)
            elseif value < 60 then
                return Color3.fromRGB(120, 230, 150)
            elseif value < 120 then
                return Color3.fromRGB(240, 210, 110)
            end
            return Color3.fromRGB(240, 110, 110)
        end

        local startedAt = os.clock()

        task.spawn(function()
            refreshPresence()
            fitIsland()

            while screenGui.Parent do
                task.wait(POLL_SECONDS)
                refreshPresence()
                fitIsland()
            end
        end)

        task.spawn(function()
            while screenGui.Parent do
                local ping = readPing()

                fpsLabel.Text = string.format('%d FPS', math.floor(fps + 0.5))
                fpsLabel.TextColor3 = fpsColor(fps)

                if ping and ping > 0 then
                    pingLabel.Text = string.format('%d MS', math.floor(ping + 0.5))
                    pingLabel.TextColor3 = pingColor(ping)
                else
                    pingLabel.Text = '-- MS'
                    pingLabel.TextColor3 = pingColor(0)
                end

                task.wait(0.25)
            end
        end)

        task.spawn(function()
            while screenGui.Parent do
                uptimeLabel.Text = formatUptime(os.clock() - startedAt)
                clockLabel.Text = localClock()
                task.wait(1)
            end
        end)

        -- keep the island fitting when the window or camera changes
        task.spawn(function()
            local lastWidth = nil

            while screenGui.Parent do
                local camera = workspace.CurrentCamera
                local width = camera and camera.ViewportSize.X or nil

                if width and width ~= lastWidth then
                    lastWidth = width
                    fitIsland()
                end

                task.wait(0.5)
            end
        end)

        if type(env.Library) == 'table'
            and typeof(env.Library.ScreenGui) == 'Instance' then
            env.Library.ScreenGui.Destroying:Connect(function()
                screenGui:Destroy()
            end)
        end

        env.prampa_HUD = screenGui

        -- live controls ---------------------------------------------------
        env.UE_SetStatus = function(status)
            manualStatus = tostring(status)
            refreshPresence()
        end

        env.UE_ClearStatus = function()
            manualStatus = nil
            refreshPresence()
        end

        env.UE_RefreshDiscord = function()
            refreshPresence()
        end

        env.UE_ToggleIsland = function()
            island.Visible = not island.Visible

            if not island.Visible then
                closePanel()
            end
        end

        env.UE_ToggleSongPicker = togglePanel
        env.UE_PlayTrack = function(value)
            if type(value) == 'number' then
                return music.play(value)
            end

            local wanted = tostring(value):lower()
            for index, track in ipairs(music.tracks) do
                if track.title:lower():find(wanted, 1, true) then
                    return music.play(index)
                end
            end

            return false
        end

        env.UE_SetTrackLoop = function(index, value)
            return music.setLoop(index, value)
        end

        env.UE_ToggleTrackLoop = function(index)
            return music.toggleLoop(index)
        end

        env.UE_NextTrack = function()
            return music.step(1)
        end

        env.UE_PrevTrack = function()
            return music.step(-1)
        end

        env.UE_SeekTrack = function(seconds)
            return music.seek(seconds)
        end

        env.UE_ToggleTrack = function()
            return music.toggle()
        end

        env.UE_ToggleShuffle = function()
            return music.toggleShuffle()
        end

        env.UE_SetShuffle = function(value)
            return music.setShuffle(value)
        end

        env.UE_ToggleMute = function()
            return music.toggleMute()
        end

        env.UE_SeekBy = function(seconds)
            return music.seekBy(seconds)
        end

        print('[' .. BRAND .. '] HUD ready - drag to move, click for the song picker.')
        if not pickerOk then
            warn('[' .. BRAND .. '] the song picker only half built; see the warning above.')
        end
        if DISCORD_ID == '' then
            print('[' .. BRAND .. '] no Discord user ID set; presence disabled.')
        end
    end

    -----------------------------------------------------------------------
    -- corner watermark
    -----------------------------------------------------------------------

    local function buildWatermark()
        local gui = Instance.new('ScreenGui')
        gui.Name = WATERMARK_NAME
        gui.ResetOnSpawn = false
        gui.IgnoreGuiInset = true
        gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
        gui.DisplayOrder = 999998
        gui.Parent = guiParent()

        local row = Instance.new('Frame')
        row.Name = 'Row'
        row.AnchorPoint = Vector2.new(1, 1)
        row.Position = UDim2.new(1, -14, 1, -12)
        row.Size = UDim2.fromOffset(0, 18)
        row.AutomaticSize = Enum.AutomaticSize.X
        row.BackgroundTransparency = 1
        row.Parent = gui

        local layout = Instance.new('UIListLayout')
        layout.FillDirection = Enum.FillDirection.Horizontal
        layout.VerticalAlignment = Enum.VerticalAlignment.Center
        layout.SortOrder = Enum.SortOrder.LayoutOrder
        layout.Padding = UDim.new(0, 6)
        layout.Parent = row

        local label = Instance.new('TextLabel')
        label.Name = 'Wordmark'
        label.BackgroundTransparency = 1
        label.Size = UDim2.fromOffset(0, 18)
        label.AutomaticSize = Enum.AutomaticSize.X
        label.Font = Enum.Font.GothamBold
        label.TextSize = 12
        label.Text = BRAND
        label.TextColor3 = Color3.fromRGB(210, 210, 222)
        label.TextTransparency = 0.6
        label.LayoutOrder = 0
        label.Parent = row

        env.prampa_Watermark = gui
    end

    -----------------------------------------------------------------------
    -- public helpers
    --   getgenv().UE_SetMenuTitle('x')
    --   getgenv().UE_SetDiscordName('x')
    --   getgenv().UE_SetStatus('dnd')
    --   getgenv().UE_ToggleIsland()
    --   getgenv().UE_ToggleSongPicker()
    --   getgenv().UE_PlayTrack(3) / UE_PlayTrack('el clasico')
    --   getgenv().UE_SetTrackLoop(3, false) / UE_ToggleTrackLoop(3)
    --   getgenv().UE_NextTrack() / UE_PrevTrack() / UE_SeekTrack(30)
    --   getgenv().UE_SeekBy(-5) / UE_ToggleShuffle() / UE_ToggleMute()
    --   getgenv().UE_ToggleMusic() / UE_SetMusicVolume(0.5)
    --   getgenv().UE_DumpTextLabels()
    -----------------------------------------------------------------------

    env.UE_ToggleMusic = function()
        return music.toggle()
    end

    env.UE_SetMusicVolume = function(value)
        music.setVolume(value)
    end

    env.UE_SetMenuTitle = function(title)
        ADDON_TITLE = tostring(title)
        applyTitle()
    end

    env.UE_SetDiscordName = function(name)
        DISCORD_NAME_OVERRIDE = tostring(name)
        if env.UE_RefreshDiscord then
            env.UE_RefreshDiscord()
        end
    end

    env.UE_DumpTextLabels = function()
        for _, gui in ipairs(guiRoots()) do
            for _, obj in ipairs(gui:GetDescendants()) do
                if obj:IsA('TextLabel') and obj.Text ~= '' then
                    print(obj:GetFullName() .. ' = ' .. string.format('%q', obj.Text))
                end
            end
        end
    end

    -----------------------------------------------------------------------
    -- ue shim: version-drift resolver + report
    --
    -- The base is a black box. When Rivals renames or moves something it
    -- stops working and says nothing useful. This sits between the base and
    -- the engine and does three jobs:
    --   * records every lookup that comes back nil, with the parent's path
    --   * resolves renames it can prove (case, separators, version suffix,
    --     a single remote sibling) and logs every substitution it makes
    --   * writes a report, so the next build is driven by data
    -----------------------------------------------------------------------

    local shim = (function()
        local TAG = '[' .. BRAND .. '] shim'

        local MAX_MISS = 800
        local MAX_CON = 400
        local MAX_SUB = 250
        local WAIT_CAP = 4
        local WATCHDOG = 25

        local MODE = tostring(env.UE_SHIM or 'safe')
        local FULL = MODE == 'full'

        local S = {
            subs = {},
            misses = {},
            missIndex = {},
            console = {},
            errorText = nil,
            aggressive = true,
            enabled = FULL,
            hooked = false,
            reported = false,
        }

        local originals = {}
        local wrappers = {}
        local aliases = {}
        local busy = false
        local pathCache = setmetatable({}, { __mode = 'k' })
        local resolveCache = setmetatable({}, { __mode = 'k' })

        local REMOTES = { RemoteEvent = true, UnreliableRemoteEvent = true, RemoteFunction = true }

        -------------------------------------------------------------------
        -- small helpers
        -------------------------------------------------------------------

        local function fullPath(inst)
            local cached = pathCache[inst]
            if cached then
                return cached
            end
            local ok, value = pcall(function()
                return inst:GetFullName()
            end)
            cached = ok and tostring(value) or '?'
            pathCache[inst] = cached
            return cached
        end

        local function norm(name)
            local text = string.lower(tostring(name))
            return (text:gsub('[^%w]', ''))
        end

        local function normVersion(name)
            local text = norm(name)
            text = text:gsub('v%d+$', '')
            return (text:gsub('%d+$', ''))
        end

        local function childrenOf(inst)
            local ok, kids = pcall(function()
                return inst:GetChildren()
            end)
            if ok and type(kids) == 'table' then
                return kids
            end
            return {}
        end

        local function isRemote(inst)
            local ok, value = pcall(function()
                return inst:IsA('RemoteEvent') or inst:IsA('RemoteFunction') or inst:IsA('UnreliableRemoteEvent')
            end)
            return ok and value == true
        end

        -------------------------------------------------------------------
        -- recording
        -------------------------------------------------------------------

        local function recordMiss(kind, parent, name, extra)
            if busy then
                return
            end
            busy = true
            local parentPath = fullPath(parent)
            local key = kind .. '|' .. parentPath .. '|' .. tostring(name)
            local row = S.missIndex[key]
            if row then
                row.count += 1
            elseif #S.misses < MAX_MISS then
                row = { kind = kind, path = parentPath, name = name, extra = extra, count = 1 }
                S.missIndex[key] = row
                S.misses[#S.misses + 1] = row
            end
            busy = false
        end

        local function recordSub(kind, parent, from, to, why)
            if busy then
                return
            end
            busy = true
            if #S.subs < MAX_SUB then
                S.subs[#S.subs + 1] = {
                    kind = kind,
                    path = fullPath(parent),
                    from = tostring(from),
                    to = tostring(to),
                    why = why or '',
                }
            end
            busy = false
        end

        -------------------------------------------------------------------
        -- resolution
        -------------------------------------------------------------------

        local function cacheResolve(parent, name, value, why)
            local bucket = resolveCache[parent]
            if not bucket then
                bucket = {}
                resolveCache[parent] = bucket
            end
            bucket[name] = value and { value = value, why = why } or false
        end

        local function fromChildren(parent, name)
            local kids = childrenOf(parent)
            if #kids == 0 then
                return nil
            end

            local lower = string.lower(tostring(name))
            local wanted = norm(name)
            local wantedVersion = normVersion(name)

            local exact, exactCount = nil, 0
            local folded, foldedCount = nil, 0
            local versioned, versionedCount = nil, 0

            for _, child in ipairs(kids) do
                local childName = tostring(child.Name)
                local childLower = string.lower(childName)

                if childLower == lower then
                    exact = child
                    exactCount += 1
                elseif norm(childName) == wanted then
                    if not folded then
                        folded = child
                    end
                    foldedCount += 1
                elseif wantedVersion ~= '' and normVersion(childName) == wantedVersion then
                    if not versioned then
                        versioned = child
                    end
                    versionedCount += 1
                end
            end

            if exactCount == 1 then
                return exact, 'case'
            end
            if foldedCount == 1 then
                return folded, 'separators'
            end
            if versionedCount == 1 then
                return versioned, 'version-suffix'
            end
            return nil
        end

        local function soleRemote(parent)
            if not S.aggressive then
                return nil
            end
            local only, count = nil, 0
            for _, child in ipairs(childrenOf(parent)) do
                if isRemote(child) then
                    only = child
                    count += 1
                    if count > 1 then
                        return nil
                    end
                end
            end
            if count == 1 then
                return only, 'sole-remote'
            end
            return nil
        end

        local function deepLookup(parent, name)
            if not S.aggressive then
                return nil
            end
            local wanted = normVersion(name)
            if wanted == '' then
                return nil
            end

            local queue = { parent }
            local head = 1
            local visited = 0
            local hit = nil
            local hits = 0

            while head <= #queue and visited < 700 do
                local current = queue[head]
                head += 1
                for _, child in ipairs(childrenOf(current)) do
                    visited += 1
                    if visited > 700 then
                        break
                    end
                    if normVersion(child.Name) == wanted then
                        hit = child
                        hits += 1
                    end
                    queue[#queue + 1] = child
                end
            end

            if hits == 1 then
                return hit, 'deep-unique'
            end
            return nil
        end

        local function resolve(parent, name)
            if not S.enabled or type(name) ~= 'string' then
                return nil
            end

            local bucket = resolveCache[parent]
            if bucket then
                local cached = bucket[name]
                if cached then
                    return cached.value, cached.why
                elseif cached == false then
                    return nil
                end
            end

            local value, why

            local mapped = aliases[name]
            if mapped then
                local kids = childrenOf(parent)
                for _, child in ipairs(kids) do
                    if tostring(child.Name) == mapped then
                        value, why = child, 'alias'
                        break
                    end
                end
                if not value then
                    value, why = deepLookup(parent, mapped)
                end
            end

            if not value then
                value, why = fromChildren(parent, name)
            end
            if not value then
                value, why = deepLookup(parent, name)
            end
            if not value then
                value, why = soleRemote(parent)
            end

            cacheResolve(parent, name, value, why)
            return value, why
        end

        -------------------------------------------------------------------
        -- console capture
        -------------------------------------------------------------------

        local function captureConsole(kind, ...)
            if #S.console >= MAX_CON then
                return
            end
            local parts = {}
            for index = 1, select('#', ...) do
                local ok, text = pcall(tostring, (select(index, ...)))
                parts[index] = ok and text or '?'
            end
            S.console[#S.console + 1] = kind .. '|' .. table.concat(parts, ' ')
        end

        local outerPrint = print
        local outerWarn = warn

        pcall(function()
            env.print = function(...)
                captureConsole('print', ...)
                return outerPrint(...)
            end
            env.warn = function(...)
                captureConsole('warn', ...)
                return outerWarn(...)
            end
        end)

        -------------------------------------------------------------------
        -- hook
        -------------------------------------------------------------------

        local function buildWrappers(baseIndex)
            for _, key in ipairs({ 'FindFirstChild', 'FindFirstChildOfClass', 'WaitForChild' }) do
                local ok, fn = pcall(function()
                    return baseIndex(game, key)
                end)
                if ok and type(fn) == 'function' then
                    originals[key] = fn
                end
            end

            if originals.FindFirstChild then
                wrappers.FindFirstChild = function(self, name, recursive)
                    local value = originals.FindFirstChild(self, name, recursive)
                    if value == nil then
                        local hit, why
                        pcall(function()
                            hit, why = resolve(self, name)
                        end)
                        if hit then
                            recordSub('ffc', self, name, hit.Name, why)
                            return hit
                        end
                        recordMiss('ffc', self, name, recursive and 'deep' or 'shallow')
                    end
                    return value
                end
            end

            if originals.WaitForChild then
                wrappers.WaitForChild = function(self, name, timeout)
                    local limit = WAIT_CAP
                    if type(timeout) == 'number' and timeout > 0 and timeout < limit then
                        limit = timeout
                    end
                    local value = originals.WaitForChild(self, name, limit)
                    if value == nil then
                        local hit, why
                        pcall(function()
                            hit, why = resolve(self, name)
                        end)
                        if hit then
                            recordSub('wait', self, name, hit.Name, why)
                            return hit
                        end
                        recordMiss('wait', self, name, tostring(limit))
                    end
                    return value
                end
            end

            if originals.FindFirstChildOfClass then
                wrappers.FindFirstChildOfClass = function(self, class)
                    local value = originals.FindFirstChildOfClass(self, class)
                    if value == nil then
                        recordMiss('class', self, class)
                    end
                    return value
                end
            end
        end

        local function observeNil(self, key)
            if busy or key == nil then
                return
            end
            busy = true
            local ok = pcall(function()
                if typeof(self) == 'Instance' then
                    recordMiss('prop', self, key)
                end
            end)
            busy = false
            if not ok then
                busy = false
            end
        end

        local function indexHook(baseIndex)
            return function(self, key)
                if not S.enabled then
                    return baseIndex(self, key)
                end
                if not S.wrappers then
                    S.wrappers = true
                    pcall(buildWrappers, baseIndex)
                end
                local value = baseIndex(self, key)
                if wrappers[key] then
                    return wrappers[key]
                end
                if value == nil and type(key) == 'string' then
                    observeNil(self, key)
                end
                return value
            end
        end

        local function install()
            if type(getrawmetatable) == 'function' then
                pcall(function()
                    local mt = getrawmetatable(game)
                    if type(mt) == 'table' and type(mt.__index) == 'function' then
                        buildWrappers(mt.__index)
                        S.wrappers = true
                    end
                end)
            end

            if type(hookmetamethod) == 'function' then
                local ok = pcall(function()
                    local original
                    original = hookmetamethod(game, '__index', indexHook(function(self, key)
                        return original(self, key)
                    end))
                end)
                if ok then
                    S.hooked = true
                    return true
                end
                return false
            end

            if type(getrawmetatable) == 'function' and type(setreadonly) == 'function' then
                local ok, done = pcall(function()
                    local mt = getrawmetatable(game)
                    if type(mt) ~= 'table' or type(mt.__index) ~= 'function' then
                        return false
                    end
                    local oldIndex = mt.__index
                    setreadonly(mt, false)
                    mt.__index = indexHook(oldIndex)
                    setreadonly(mt, true)
                    return true
                end)
                if ok and done then
                    S.hooked = true
                    return true
                end
            end

            return false
        end

        -------------------------------------------------------------------
        -- report
        -------------------------------------------------------------------

        local function treeLines()
            local lines = {}
            local count = 0
            local function walk(root, maxDepth, cap, base)
                local queue = { { inst = root, depth = 0, path = base } }
                local head = 1
                while head <= #queue and count < cap do
                    local item = queue[head]
                    head += 1
                    local inst = item.inst
                    count += 1
                    local className = '?'
                    local name = '?'
                    pcall(function()
                        className = inst.ClassName
                        name = inst.Name
                    end)
                    lines[#lines + 1] = 'NODE|' .. item.path .. name .. '|' .. className
                    if item.depth < maxDepth then
                        for _, child in ipairs(childrenOf(inst)) do
                            queue[#queue + 1] = {
                                inst = child,
                                depth = item.depth + 1,
                                path = item.path .. name .. '.',
                            }
                        end
                    end
                end
            end

            pcall(function()
                walk(game:GetService('ReplicatedStorage'), 4, 1200, '')
            end)
            pcall(function()
                walk(game:GetService('Workspace'), 3, 900, '')
            end)
            return lines
        end

        local function report(reason)
            local lines = {}
            local function add(text)
                lines[#lines + 1] = text
            end

            add('SHIM|' .. BUILD_ID .. '|' .. os.date('%Y-%m-%d %H:%M:%S'))
            add(table.concat({
                'META',
                tostring(game.PlaceId),
                tostring(game.GameId),
                tostring(identifyexecutor and identifyexecutor() or '?'),
                tostring(env.Library ~= nil),
                tostring(S.hooked),
            }, '|'))

            for _, row in ipairs(S.subs) do
                add('SUB|' .. row.kind .. '|' .. row.from .. '|' .. row.to .. '|' .. row.why .. '|' .. row.path)
            end
            for _, row in ipairs(S.misses) do
                add('MISS|' .. row.kind .. '|' .. tostring(row.name) .. '|' .. row.path .. '|' .. tostring(row.extra or '') .. '|' .. row.count)
            end
            for _, line in ipairs(S.console) do
                add('CON|' .. line)
            end
            if S.errorText then
                add('ERR|' .. S.errorText)
            end
            for _, line in ipairs(treeLines()) do
                add(line)
            end
            add('END|' .. #lines)

            local text = table.concat(lines, '\n')
            local name = 'ue_shim_' .. os.date('%Y%m%d_%H%M%S') .. '.txt'
            local wrote = false
            if writefile then
                wrote = pcall(writefile, name, text)
            end

            S.reported = true
            outerPrint(TAG .. ': ' .. tostring(reason) .. ' -> ' .. (wrote and name or 'no writefile'))
            outerPrint(TAG .. ': ' .. #S.subs .. ' aliases, ' .. #S.misses .. ' misses, ' .. #S.console .. ' console lines')

            local shown = 0
            for _, row in ipairs(S.misses) do
                if shown >= 10 then
                    break
                end
                shown += 1
                outerPrint(TAG .. ': miss ' .. row.kind .. ' ' .. tostring(row.name) .. ' in ' .. row.path)
            end

            return name
        end

        -------------------------------------------------------------------
        -- public surface
        -------------------------------------------------------------------

        local function export(name, value)
            pcall(function()
                env[name] = value
            end)
        end

        export('UE_ShimReport', function(reason)
            return report(reason or 'manual')
        end)

        export('UE_ShimAlias', function(from, to)
            aliases[tostring(from)] = tostring(to)
            resolveCache = setmetatable({}, { __mode = 'k' })
            outerPrint(TAG .. ': alias ' .. tostring(from) .. ' -> ' .. tostring(to))
        end)

        export('UE_ShimAggressive', function(flag)
            S.aggressive = flag ~= false
            return S.aggressive
        end)

        export('UE_ShimOff', function()
            S.enabled = false
        end)

        S.mode = MODE
        local okHook = false
        if FULL then
            okHook = install()
        end

        outerPrint(TAG .. ': mode=' .. MODE .. '  build=' .. BUILD_ID)
        if FULL then
            outerPrint(TAG .. ': hook ' .. (okHook and 'installed' or 'unavailable, reporting only'))
        end

        -- written before the base boots, so a crash still leaves a fingerprint
        if writefile then
            pcall(writefile, 'ue_shim_boot.txt', table.concat({
                'BOOT|' .. BUILD_ID .. '|' .. MODE .. '|' .. tostring(okHook) .. '|' .. os.date('%Y-%m-%d %H:%M:%S'),
                'META|' .. tostring(game.PlaceId) .. '|' .. tostring(game.GameId),
            }, '\n'))
            outerPrint(TAG .. ': boot file ue_shim_boot.txt')
        end

        -------------------------------------------------------------------
        -- boot capture
        -------------------------------------------------------------------

        if type(runApplication) == 'function' then
            local originalRun = runApplication
            runApplication = function(...)
                outerPrint(TAG .. ': entering base boot')
                local results = table.pack(xpcall(originalRun, function(err)
                    local okTrace, trace = pcall(debug.traceback, '', 2)
                    return tostring(err) .. '\n' .. (okTrace and tostring(trace) or '')
                end))
                if not results[1] then
                    S.errorText = tostring(results[2])
                    pcall(report, 'boot error')
                    error(results[2], 0)
                end
                outerPrint(TAG .. ': base boot returned')
                return table.unpack(results, 2, results.n)
            end
        end

        task.spawn(function()
            task.wait(WATCHDOG)
            local healthy = false
            pcall(function()
                healthy = type(env.Library) == 'table'
                    and typeof(env.Library.ScreenGui) == 'Instance'
            end)
            if not healthy and not S.reported then
                pcall(report, 'no menu after ' .. WATCHDOG .. 's')
            end
        end)

        return S
    end)()

    -----------------------------------------------------------------------
    -- boot
    -----------------------------------------------------------------------

    task.spawn(function()
        local function step(label, fn)
            local ok, err = pcall(fn)
            if not ok then
                warn('[' .. BRAND .. '] ' .. label .. ' failed: ' .. tostring(err))
            end
            return ok
        end

        local waited = 0

        while waited < 300 do
            if type(env.Library) == 'table'
                and typeof(env.Library.ScreenGui) == 'Instance' then
                step('title hook', watchTitle)
                step('music player', prepareMusic)
                step('island', buildIsland)
                step('menu raise', raiseMenu)

                if SHOW_WATERMARK then
                    step('watermark', buildWatermark)
                end

                print('[' .. BRAND .. '] build ' .. BUILD_ID .. ' HUD ready')

                task.spawn(function()
                    local startIndex = tonumber(config.track) or 1
                    if not music.tracks[startIndex] then
                        startIndex = 1
                    end

                    local ok, err = pcall(music.play, startIndex)
                    if not ok then
                        warn('[' .. BRAND .. '] autoplay failed: ' .. tostring(err))
                    end
                end)
                return
            end

            task.wait(0.2)
            waited += 0.2
        end

        warn('[' .. BRAND .. '] getgenv().Library never appeared; HUD not created.')
    end)
end
-- <<< prampa addon <<<
"""


def parse_hex(value: str) -> "tuple[int, int, int]":
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        fail("ACCENT_HEX must be six hex digits, e.g. 7C5CFF")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def main(argv: "list[str]") -> int:
    # the console codepage cannot always render track titles; never crash on it
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    here = Path(__file__).resolve().parent
    source = Path(argv[1]).expanduser() if len(argv) > 1 else here / SOURCE_NAME
    output = Path(argv[2]).expanduser() if len(argv) > 2 else here / OUTPUT_NAME

    # ---- resolve Discord settings ---------------------------------------
    raw_id = DISCORD_USER_ID.strip()
    raw_name = DISCORD_NAME.strip()

    if raw_id == PLACEHOLDER_ID:
        raw_id = ""

    if TOKEN_RE.match(raw_id):
        fail(
            "DISCORD_USER_ID looks like a real Discord token.\n"
            "       No token is used anywhere in this addon. Presence is read from\n"
            "       Lanyard, which only needs your numeric user ID (17-20 digits).\n"
            "       Right click your name in Discord with Developer Mode enabled and\n"
            "       choose 'Copy User ID'."
        )

    if TOKEN_RE.match(raw_name):
        fail("DISCORD_NAME looks like a real Discord token; put a plain name.")

    presence_id = ""
    if raw_id:
        if raw_id.isdigit() and 15 <= len(raw_id) <= 25:
            presence_id = raw_id
        elif not raw_name:
            raw_name = raw_id
            print(
                "note: DISCORD_USER_ID is not numeric, so it will be shown as a "
                "plain name and Lanyard presence is disabled.",
                file=sys.stderr,
            )

    # ---- validate the track list ----------------------------------------
    if not (MUSIC_BASE.startswith("https://") or MUSIC_BASE.startswith("http://")):
        fail("MUSIC_BASE must be a full http(s) URL (keep the trailing '/').")

    tracks = []
    for entry in MUSIC_TRACKS:
        if not isinstance(entry, (tuple, list)) or len(entry) not in (2, 3):
            fail("each MUSIC_TRACKS entry must be (title, file) or (title, file, seconds).")
        title = str(entry[0]).strip()
        file = str(entry[1]).strip()
        if not title or not file:
            fail("MUSIC_TRACKS entries need both a title and a file.")
        if "\n" in title or "\r" in title:
            fail("track titles must be a single line: %r" % title)

        duration = None
        if len(entry) == 3:
            try:
                duration = float(entry[2])
            except (TypeError, ValueError):
                fail("track duration must be a number of seconds: %r" % (entry[2],))
            if duration <= 0:
                fail("track duration must be positive: %r" % (entry[2],))

        tracks.append((title, file, duration))

    if len(tracks) > 12:
        fail("MUSIC_TRACKS holds %d tracks; the picker is limited to 12." % len(tracks))

    seen_files = set()
    for _, file, _duration in tracks:
        key = file.lower()
        if key in seen_files:
            fail("duplicate track file in MUSIC_TRACKS: %s" % file)
        seen_files.add(key)

    try:
        music_volume = float(MUSIC_VOLUME)
    except (TypeError, ValueError):
        fail("MUSIC_VOLUME must be a number between 0.0 and 1.0.")
    if not (0.0 <= music_volume <= 1.0):
        fail("MUSIC_VOLUME must be between 0.0 and 1.0 (0.25 = 25 %).")

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", BRAND):
        fail("BRAND must be 1-32 chars of letters, digits, '_', '-' or '.'.")

    accent = parse_hex(ACCENT_HEX)

    # ---- guard rails ----------------------------------------------------
    if not source.is_file():
        fail("source file not found: %s" % source)

    for label, value in (
        ("MENU_TITLE", MENU_TITLE),
        ("DISCORD_NAME", raw_name),
        ("BRAND", BRAND),
    ):
        if "\n" in value or "\r" in value:
            fail("%s must be a single line." % label)

    with open(source, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()

    newline = "\r\n" if "\r\n" in raw else "\n"

    if any(marker in raw for marker in STALE_MARKERS):
        fail(
            "the source file already contains the addon block.\n"
            "       Run this against a clean ue-v2-cracked.luau.txt."
        )

    if raw.count("return runApplication()") != 1:
        fail("could not find exactly one 'return runApplication()' anchor.")

    text = raw
    report = []

    # ---- 1. rebrand the shared-env key ----------------------------------
    old_key = lua_str(OLD_TITLE)
    new_key = lua_str(BRAND)

    guard_old = "rawget(sharedEnv, %s)" % old_key
    guard_new = "rawget(sharedEnv, %s)" % new_key
    store_old = "sharedEnv[%s] = control" % old_key
    store_new = "sharedEnv[%s] = control" % new_key

    key_hits = text.count(guard_old) + text.count(store_old)
    text = text.replace(guard_old, guard_new).replace(store_old, store_new)
    report.append("env key    : %d replacement(s) -> %r" % (key_hits, BRAND))
    if key_hits != 2:
        print(
            "warning: expected 2 env-key replacements, got %d." % key_hits,
            file=sys.stderr,
        )

    # ---- 2. drop the compiler directives -------------------------------
    text, directive_hits = re.subn(
        r"^--!(?:nocheck|native)[ \t]*\r?\n", "", text, flags=re.M
    )
    report.append("directives : %d removed" % directive_hits)

    # ---- 3. drop the ascii-art banner -----------------------------------
    art_start = text.find("--[[")
    art_end = text.find("]]", art_start) if art_start != -1 else -1
    art_ok = (
        art_start != -1
        and art_end != -1
        and art_start < 400
        and (art_end - art_start) < 6000
        and ("@@@@" in text[art_start:art_end] or ",,,,,," in text[art_start:art_end])
    )

    if art_ok:
        banner = newline.join(
            [
                "-- ================================================================",
                "--  %s build" % BRAND,
                "--  generated by patch_ue2.py - do not redistribute",
                "-- ================================================================",
            ]
        )
        text = text[:art_start] + banner + newline + text[art_end + 2 :]
        report.append("ascii art  : removed")
    else:
        report.append("ascii art  : not found (left as-is)")

    # ---- 4. rebrand the console banner ----------------------------------
    banner_re = re.compile(r"print\[\[[\s\S]{0,3000}?\]\]")
    new_print = "print(%s)" % lua_str("[%s] build loaded" % BRAND)
    text, print_hits = banner_re.subn(lambda m: new_print, text, count=1)
    report.append("console    : %d banner(s) rebranded" % print_hits)

    # ---- 5. rewrite the two constant-pool strings -----------------------
    pool_re = re.compile(r"(\[\d+\]\s*=\s*)" + re.escape(old_key))
    text, pool_hits = pool_re.subn(lambda m: m.group(1) + lua_str(MENU_TITLE), text)
    report.append("title      : %d constant(s) -> %r" % (pool_hits, MENU_TITLE))

    # ---- 5b. rebrand the theme JSON labels -------------------------------
    theme_old = '"ItemType":"%s"' % OLD_TITLE
    theme_hits = text.count(theme_old)
    text = text.replace(theme_old, '"ItemType":"%s"' % BRAND)
    report.append("themes     : %d label(s) -> %r" % (theme_hits, BRAND))

    # ---- 6. inject the addon --------------------------------------------
    def lua_number(value: float) -> str:
        text_value = ("%.3f" % value).rstrip("0").rstrip(".")
        return text_value or "0"

    track_lines = []
    for title, file, duration in tracks:
        if duration is None:
            track_lines.append(
                "        { title = %s, file = %s }," % (lua_str(title), lua_str(file))
            )
        else:
            track_lines.append(
                "        { title = %s, file = %s, duration = %s },"
                % (lua_str(title), lua_str(file), lua_number(duration))
            )

    lua_tracks = ("{\n" + "\n".join(track_lines) + "\n    }") if track_lines else "{}"

    addon = ADDON_TEMPLATE.replace("@@BRAND@@", lua_str(BRAND))
    addon = addon.replace("@@TITLE@@", lua_str(MENU_TITLE))
    addon = addon.replace("@@DISCORD_ID@@", lua_str(presence_id))
    addon = addon.replace("@@DISCORD_NAME@@", lua_str(raw_name))
    addon = addon.replace("@@MUSIC_BASE@@", lua_str(MUSIC_BASE))
    addon = addon.replace("@@MUSIC_TRACKS@@", lua_tracks)
    addon = addon.replace("@@MUSIC_VOLUME@@", "%.3f" % music_volume)
    addon = addon.replace("@@ACCENT@@", "Color3.fromRGB(%d, %d, %d)" % accent)
    addon = addon.replace("@@WATERMARK@@", "true" if SHOW_WATERMARK else "false")

    # short, stable fingerprint so the console always shows which build runs
    build_id = hashlib.sha1(addon.replace("@@BUILD_ID@@", "x").encode("utf-8")).hexdigest()[:8]
    addon = addon.replace("@@BUILD_ID@@", lua_str(build_id))

    addon = addon.strip("\r\n").replace("\r\n", "\n").replace("\n", newline) + newline

    if "@@" in addon:
        fail("a placeholder was left unresolved in the addon block.")

    anchor = text.rfind("return runApplication()")
    line_start = text.rfind("\n", 0, anchor) + 1
    text = text[:line_start] + addon + text[line_start:]

    # ---- write ----------------------------------------------------------
    with open(output, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)

    # keep the GitHub filename in sync so there is no manual copy step
    alias = output.parent / ALIAS_NAME if ALIAS_NAME else None
    alias_written = 0
    if alias is not None and alias.resolve() != output.resolve():
        try:
            with open(alias, "wb") as handle:
                handle.write(text.encode("utf-8"))
            alias_written = alias.stat().st_size
        except OSError as error:
            print("warning: could not write %s: %s" % (alias, error), file=sys.stderr)

    # ---- verify ---------------------------------------------------------
    with open(output, "r", encoding="utf-8", newline="") as handle:
        check = handle.read()

    problems = []
    if check.count(MARKER) != 1:
        problems.append("addon marker count != 1")
    if check.count("return runApplication()") != 1:
        problems.append("'return runApplication()' count != 1")
    if "@@" in check[check.find(MARKER) :]:
        problems.append("unresolved placeholder")
    if lua_str(MENU_TITLE) not in check:
        problems.append("title literal missing")
    if "--!native" in check or "--!nocheck" in check:
        problems.append("compiler directives still present")
    if check.count("sharedEnv[%s] = control" % lua_str(BRAND)) != 1:
        problems.append("brand env key missing")
    if not check.rstrip().endswith("return runApplication()"):
        problems.append("file no longer ends with 'return runApplication()'")

    print("source : %s (%d bytes)" % (source, len(raw.encode("utf-8"))))
    print("output : %s (%d bytes)" % (output, len(check.encode("utf-8"))))
    if alias_written:
        print("alias  : %s (%d bytes)" % (alias, alias_written))
    print("brand  : %s   accent: #%02X%02X%02X" % ((BRAND,) + accent))
    print("build  : %s" % build_id)
    print("title  : %s" % MENU_TITLE)
    print("user id: %s" % (presence_id or "(none - presence disabled)"))
    print("tracks : %d" % len(tracks))
    for index, (title, file, duration) in enumerate(tracks, start=1):
        seconds = ""
        if duration is not None:
            seconds = "  %d:%02d" % (int(duration) // 60, int(duration) % 60)
        print("  %2d. %-28s %s%s" % (index, title, file, seconds))
    for line in report:
        print("  " + line)
    print("anchor : inserted at line %d" % (check[: check.find(MARKER)].count("\n") + 1))

    if pool_hits != 2:
        print(
            "warning: expected 2 constant-pool rewrites, got %d. The visible "
            "title fallback still runs at startup." % pool_hits,
            file=sys.stderr,
        )

    if problems:
        print("verify : FAILED -> " + ", ".join(problems), file=sys.stderr)
        return 1

    print("verify : ok")

    if MENU_TITLE == PLACEHOLDER_TITLE:
        print("\nnote: MENU_TITLE is still the placeholder.")

    if presence_id == "":
        print(
            "\nnote: no numeric Discord user ID set, so the HUD cannot show\n"
            "      presence. Join https://discord.gg/lanyard and put your user ID\n"
            "      in DISCORD_USER_ID."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
