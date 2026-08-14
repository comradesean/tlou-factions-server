meta:
  id: opcodes
  license: CC0-1.0
doc: |
  NetEventType id -> name enum. STATUS: numeric IDs CONFIRMED (Ghidra, session 1);
  per-opcode wire *payload* layout is still unconfirmed.

  Recovered by locating a 116-slot pointer table in memory (base 0x012238e0,
  4-byte/32-bit pointers, one entry per NetEventType value) whose targets are
  the NetEvent* name strings already catalogued in
  protos/pending/netevent_catalog.md, confirmed by finding the accessor
  function that indexes it: `FUN_00388b80(int id) { return table[id]; }`
  (i.e. GetNetEventName(NetEventType id)). Entries are in exact enum
  declaration order, terminated by a `kNumNetEvents` sentinel = 115 (confirming
  the count). Full recovery method and raw output: research/notes/ghidra-opcode-recovery.md.

  Corroborating evidence that the wire/in-memory representation is a single
  byte (fits easily - max value 114): callers of the accessor
  (`FUN_00ace694` @ 0x00ace694, `FUN_00acecd0` @ 0x00acecd0, both in what looks
  like a network event queue processing loop) read the id via
  `*(undefined1 *)(*piVar17 + 4)` - an explicit 1-byte load - before passing it
  to the name lookup. This is evidence about the in-process representation,
  not yet a confirmed wire format - see protos/common/packet_header.ksy.

  One discrepancy from the original strings-only catalog: `NetEventCharacterMove`
  (in protos/pending/netevent_catalog.md) is NOT one of these 115 table
  entries - it's presumably a related class/symbol name rather than a distinct
  NetEventType value. Not otherwise investigated this session.

  Known false leads (do NOT confuse with this table): the assert strings
  "Out of range Opcode type of 0x%X." / "Unimplemented Opcode type of 0x%X."
  belong to an unrelated audio "grains" subsystem (src/common/grains.cpp,
  0-53 range); "%p:%3u - UNKNOWN OPCODE" belongs to what looks like a
  general script/bytecode VM (0-67 range). Neither is the network protocol.
doc-ref: ../../docs/protocol/README.md
enums:
  net_event_type:
    0: start_connection  # NetEventStartConnection
    1: connection_done  # NetEventConnectionDone
    2: load_level  # NetEventLoadLevel
    3: ready_to_start  # NetEventReadyToStart
    4: start_game  # NetEventStartGame
    5: end_game  # NetEventEndGame
    6: end_round  # NetEventEndRound
    7: emit_projectile_bullet  # NetEventEmitProjectileBullet
    8: spawn_projectile_throwable  # NetEventSpawnProjectileThrowable
    9: kill_projectile_throwable  # NetEventKillProjectileThrowable
    10: emit_grenade  # NetEventEmitGrenade
    11: spawn_explosion  # NetEventSpawnExplosion
    12: grenade_start_fuse  # NetEventGrenadeStartFuse
    13: player_move  # NetEventPlayerMove
    14: npc_move  # NetEventNpcMove
    15: attack_projectile  # NetEventAttackProjectile
    16: attack_explosion  # NetEventAttackExplosion
    17: kill_info  # NetEventKillInfo
    18: assign_team  # NetEventAssignTeam
    19: assign_team_desc  # NetEventAssignTeamDesc
    20: assign_team_done  # NetEventAssignTeamDone
    21: request_interact  # NetEventRequestInteract
    22: approved_interact  # NetEventApprovedInteract
    23: denied_interact  # NetEventDeniedInteract
    24: on_interact  # NetEventOnInteract
    25: end_interact  # NetEventEndInteract
    26: add_dropped_interactable  # NetEventAddDroppedInteractable
    27: remove_interactable  # NetEventRemoveInteractable
    28: set_interactable_ammo  # NetEventSetInteractableAmmo
    29: respawn_player  # NetEventRespawnPlayer
    30: signal_respawn_player  # NetEventSignalRespawnPlayer
    31: secure_carry_object  # NetEventSecureCarryObject
    32: secured_flag_score  # NetEventSecuredFlagScore
    33: start_pack_or_deploy  # NetEventStartPackOrDeploy
    34: stop_pack_or_deploy  # NetEventStopPackOrDeploy
    35: spawn_carry_object  # NetEventSpawnCarryObject
    36: carry_object_drop  # NetEventCarryObjectDrop
    37: carry_object_stop_move  # NetEventCarryObjectStopMove
    38: npc_spawn  # NetEventNpcSpawn
    39: npc_kill  # NetEventNpcKill
    40: breakable_attack_projectile  # NetEventBreakableAttackProjectile
    41: breakable_attack_projectile_with_results  # NetEventBreakableAttackProjectileWithResults
    42: breakable_attack_explosion  # NetEventBreakableAttackExplosion
    43: breakable_attack_explosion_with_results  # NetEventBreakableAttackExplosionWithResults
    44: player_info  # NetEventPlayerInfo
    45: message  # NetEventMessage
    46: event  # NetEventEvent
    47: revive  # NetEventRevive
    48: revive_finished  # NetEventReviveFinished
    49: revive_credit  # NetEventReviveCredit
    50: play_vox  # NetEventPlayVox
    51: simple_snapshot  # NetEventSimpleSnapshot
    52: simple_snapshot_phys_fx  # NetEventSimpleSnapshotPhysFx
    53: npc_piecewise_health_depleted  # NetEventNpcPiecewiseHealthDepleted
    54: player_death_cleanup  # NetEventPlayerDeathCleanup
    55: complete_task  # NetEventCompleteTask
    56: start_net_task  # NetEventStartNetTask
    57: player_health  # NetEventPlayerHealth
    58: heal  # NetEventHeal
    59: kick_griefer  # NetEventKickGriefer
    60: coop_team_failed  # NetEventCoopTeamFailed
    61: abort_interact  # NetEventAbortInteract
    62: spawn_entity  # NetEventSpawnEntity
    63: kill_entity  # NetEventKillEntity
    64: animation_sync  # NetEventAnimationSync
    65: sync_stats  # NetEventSyncStats
    66: sync_stats_player  # NetEventSyncStatsPlayer
    67: sync_carry_objects  # NetEventSyncCarryObjects
    68: sync_carry_object_stands  # NetEventSyncCarryObjectStands
    69: sync_weapon_pickups  # NetEventSyncWeaponPickups
    70: sync_breakable  # NetEventSyncBreakable
    71: sync_players  # NetEventSyncPlayers
    72: request_ownership  # NetEventRequestOwnership
    73: transfer_ownership  # NetEventTransferOwnership
    74: deny_ownership_request  # NetEventDenyOwnershipRequest
    75: net_go  # NetEventNetGo
    76: swap_booster  # NetEventSwapBooster
    77: start_melee  # NetEventStartMelee
    78: abort_melee  # NetEventAbortMelee
    79: attack_melee_damage  # NetEventAttackMeleeDamage
    80: set_melee_history  # NetEventSetMeleeHistory
    81: reset_melee_history  # NetEventResetMeleeHistory
    82: melee_assist  # NetEventMeleeAssist
    83: melee_block  # NetEventMeleeBlock
    84: npd_stat  # NetEventNpdStat
    85: debug  # NetEventDebug
    86: net_set  # NetEventNetSet
    87: client_net_go  # NetEventClientNetGo
    88: late_join_sync_done  # NetEventLateJoinSyncDone
    89: late_join_sync_done_host  # NetEventLateJoinSyncDoneHost
    90: phase_snapshot  # NetEventPhaseSnapshot
    91: sync_odd_lives  # NetEventSyncOddLives
    92: debug_caption  # NetEventDebugCaption
    93: npc_hit_reaction  # NetEventNpcHitReaction
    94: npc_death_reaction  # NetEventNpcDeathReaction
    95: npc_set_host  # NetEventNpcSetHost
    96: npc_on_screen  # NetEventNpcOnScreen
    97: set_tension  # NetEventSetTension
    98: audio_gameplay_event  # NetEventAudioGameplayEvent
    99: give_item  # NetEventGiveItem
    100: item_received  # NetEventItemReceived
    101: increment_tally_stat  # NetEventIncrementTallyStat
    102: increment_score  # NetEventIncrementScore
    103: set_player_exposed  # NetEventSetPlayerExposed
    104: add_net_marker  # NetEventAddNetMarker
    105: player_left  # NetEventPlayerLeft
    106: dismember  # NetEventDismember
    107: kill_all_mines  # NetEventKillAllMines
    108: spawn_visibility_blocker  # NetEventSpawnVisibilityBlocker
    109: sync_proxy_mine  # NetEventSyncProxyMine
    110: explode  # NetEventExplode
    111: set_weapon_upgrade_level  # NetEventSetWeaponUpgradeLevel
    112: debug_swap_part  # NetEventDebugSwapPart
    113: emit_arrow  # NetEventEmitArrow
    114: spawn_armor_destruction  # NetEventSpawnArmorDestruction
    # 115 = kNumNetEvents: sentinel/count, not a real opcode
