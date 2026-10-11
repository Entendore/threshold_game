import math
import numpy as np
import pygame
from OpenGL.GL import *
from core import WIDTH, HEIGHT, MAX_TRAIL, SaveSystem
from entities import Player, Camera
from level import LevelLoader, BoxShape, CircleShape

class BaseState:
    def __init__(self, engine):
        self.engine = engine
    def enter(self, data=None): pass
    def exit(self): pass
    def handle_event(self, event): pass
    def update(self, dt): pass
    def draw(self): pass
    
    def _set_scene_uniforms(self, level, player_pos, player_scale, player_angle, player_radius, player_dash_cd, player_thrust, player_invuln, player_color, orbs_collected, checkpoint_active, goal_active):
        shader = self.engine.shader
        shader.set_3f("uBgColor", level.bg_color[0], level.bg_color[1], level.bg_color[2])
        shader.set_3f("uAccentColor", level.accent_color[0], level.accent_color[1], level.accent_color[2])
        shader.set_2f("uPlayerPos", player_pos[0], player_pos[1])
        shader.set_2f("uPlayerScale", player_scale[0], player_scale[1])
        shader.set_1f("uPlayerRadius", player_radius)
        shader.set_1f("uPlayerAngle", player_angle)
        shader.set_1f("uPlayerDashCD", player_dash_cd)
        shader.set_1f("uPlayerThrust", player_thrust)
        shader.set_1f("uPlayerInvuln", player_invuln)
        shader.set_3f("uPlayerColor", player_color[0], player_color[1], player_color[2])
        
        all_boxes = level.boxes + [ms.shape for ms in level.moving_shapes if isinstance(ms.shape, BoxShape)]
        box_data = []; box_cols = []; box_rots = []
        for b in all_boxes:
            box_data.extend([b.center[0], b.center[1], b.half_size[0], b.half_size[1]])
            box_cols.extend(b.color)
            box_rots.append(b.rot)
        shader.set_4fv("uBoxes", max(1, len(box_data)//4), box_data if box_data else [0,0,0,0])
        shader.set_3fv("uBoxColors", max(1, len(box_cols)//3), box_cols if box_cols else [0,0,0])
        shader.set_1fv("uBoxRots", max(1, len(box_rots)), box_rots if box_rots else [0.0])
        shader.set_1i("uBoxCount", len(all_boxes))
        
        all_circs = level.circles + [ms.shape for ms in level.moving_shapes if isinstance(ms.shape, CircleShape)]
        circ_data = []; circ_cols = []
        for c in all_circs:
            circ_data.extend([c.center[0], c.center[1], c.radius, c.bounce])
            circ_cols.extend(c.color)
        shader.set_4fv("uCircles", max(1, len(circ_data)//4), circ_data if circ_data else [0,0,0,0])
        shader.set_3fv("uCircleColors", max(1, len(circ_cols)//3), circ_cols if circ_cols else [0,0,0])
        shader.set_1i("uCircleCount", len(all_circs))
        
        las_data = []; las_phases = []
        for l in level.lasers:
            las_data.extend([l["center"][0], l["center"][1], l["speed"], l["length"]])
            las_phases.append(l["phase"])
        shader.set_4fv("uLasers", max(1, len(las_data)//4), las_data if las_data else [0,0,0,0])
        shader.set_1fv("uLaserPhases", max(1, len(las_phases)), las_phases if las_phases else [0.0])
        shader.set_1i("uLaserCount", len(level.lasers))
        
        orb_data = []
        for o in level.orbs:
            orb_data.extend([o[0], o[1], o[2]])
        shader.set_3fv("uOrbs", max(1, len(orb_data)//3), orb_data if orb_data else [0,0,0])
        shader.set_1iv("uOrbCollected", max(1, len(orbs_collected)), orbs_collected if orbs_collected else [0])
        shader.set_1i("uOrbCount", len(level.orbs))
        
        cp_data = []
        for cp in level.checkpoints:
            cp_data.extend([cp[0], cp[1], cp[2]])
        shader.set_3fv("uCheckpoints", max(1, len(cp_data)//3), cp_data if cp_data else [0,0,0])
        shader.set_1iv("uCheckpointActive", max(1, len(checkpoint_active)), checkpoint_active if checkpoint_active else [0])
        shader.set_1i("uCheckpointCount", len(level.checkpoints))
        
        shader.set_1f("uGoalActive", 1.0 if goal_active else 0.0)
        shader.set_2f("uGoalPos", level.goal[0], level.goal[1])

class MenuState(BaseState):
    def enter(self, data=None):
        self.menu_idx = data.get("menu_idx", 0) if data else 0
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif event.key in (pygame.K_w, pygame.K_UP):
                self.menu_idx = (self.menu_idx - 1) % len(self.engine.levels)
                self.engine.audio.play('select', 0.3)
            elif event.key in (pygame.K_s, pygame.K_DOWN):
                self.menu_idx = (self.menu_idx + 1) % len(self.engine.levels)
                self.engine.audio.play('select', 0.3)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if str(self.menu_idx) in self.engine.save["unlocked"]:
                    self.engine.change_state("PLAYING", {"level_idx": self.menu_idx})
    def update(self, dt):
        LevelLoader.update(self.engine.levels[self.menu_idx], self.engine.time)
    def draw(self):
        shader = self.engine.shader
        mesh = self.engine.mesh
        shader.use()
        
        rm = 1.0 if self.engine.reduce_motion else 0.0
        shader.set_1f("uTime", self.engine.time)
        shader.set_2f("uResolution", WIDTH, HEIGHT)
        shader.set_2f("uCamOffset", 0.0, 0.0)
        shader.set_1f("uZoom", 1.0)
        shader.set_1f("uReduceMotion", rm)
        shader.set_1f("uMenuMode", 1.0)
        
        preview = self.engine.levels[self.menu_idx]
        self._set_scene_uniforms(preview, np.array([-1000.0, -1000.0]), np.array([1.0, 1.0]), 0.0, 12.0, 0.0, 0.0, preview.player_color, [0]*len(preview.orbs), [0]*len(preview.checkpoints), True)
        
        shader.set_3fv("uTrail", MAX_TRAIL, np.zeros(MAX_TRAIL * 3, dtype=np.float32))
        shader.set_1i("uTrailCount", 0)
        shader.set_1f("uDamageFlash", 0.0)
        shader.set_1f("uLevelClearFlash", 0.0)
        shader.set_1f("uRespawnFlash", 0.0)
        
        mesh.draw()
        self._draw_ui()
        
    def _draw_ui(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        text = self.engine.text
        text.render_quad(0, 0, WIDTH, HEIGHT, (0, 0, 0, 130))
        
        hue_t = self.engine.time * 0.4
        r = int(180 + 75 * math.sin(hue_t))
        g = int(100 + 80 * math.sin(hue_t + 2.0))
        b = int(200 + 55 * math.sin(hue_t + 4.0))
        text.render_centered("THRESHOLD", WIDTH//2, 90, text.font_huge, (r, g, b))
        text.render_centered("A Surreal Journey Through Zones", WIDTH//2, 165, text.font_md, (200, 200, 230))
        text.render_centered("Select a Zone:", WIDTH//2, 230, text.font, (255, 255, 255))
        
        y = 280
        for i, lvl in enumerate(self.engine.levels):
            is_unlocked = str(i) in self.engine.save["unlocked"]
            selected = (i == self.menu_idx)
            
            if is_unlocked:
                if selected:
                    color = (255, 235, 110)
                    prefix = "\u25B6  "; suffix = "  \u25C0"
                else:
                    color = (140, 140, 170)
                    prefix = "   "; suffix = "   "
                name = f"{prefix}{i+1}. {lvl.name}{suffix}"
            else:
                color = (80, 80, 80)
                name = f"    \u1F512 LOCKED    "
                
            text.render_centered(name, WIDTH//2, y, text.font_md, color)
            
            if is_unlocked and str(i) in self.engine.save["best_times"]:
                best_time = self.engine.save["best_times"][str(i)]
                mins = int(best_time // 60); secs = best_time % 60
                text.render_centered(f"Best: {mins:01d}:{secs:05.2f}", WIDTH//2, y + 18, text.font_sm, (100, 200, 150))
            y += 46
            
        text.render_centered("A/D Rotate   |   W Thrust   |   S Brake   |   SPACE Dash",
                              WIDTH//2, HEIGHT - 70, text.font, (170, 170, 200))
        text.render_centered("UP/DOWN Navigate   |   ENTER Play   |   ESC Quit",
                              WIDTH//2, HEIGHT - 40, text.font, (170, 170, 200))
        glDisable(GL_BLEND)

class PlayState(BaseState):
    def enter(self, data=None):
        self.level_idx = data["level_idx"]
        self.level = self.engine.levels[self.level_idx]
        
        self.player = Player(pos=self.level.spawn.copy(), angle=self.level.spawn_angle, color=self.level.player_color)
        self.camera = Camera()
        
        self.orbs_collected = [0] * len(self.level.orbs)
        self.checkpoint_active = [0] * len(self.level.checkpoints)
        self.current_checkpoint = -1
        self.goal_active = (len(self.level.orbs) == 0)
        
        self.level_time = 0.0
        self.zone_title_timer = 3.0
        self.respawn_text_timer = 0.0
        self.damage_flash = 0.0
        self.level_clear_flash = 0.0
        self.respawn_flash = 0.0
        self.hit_stop = 0.0
        
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.engine.change_state("PAUSED")
            elif event.key == pygame.K_SPACE:
                self.player.buffer_dash()
                
    def update(self, dt):
        sim_dt = dt
        if self.hit_stop > 0:
            self.hit_stop -= dt
            sim_dt = 0
            
        self.level_time += sim_dt
        LevelLoader.update(self.level, self.engine.time)
        
        keys = self.engine.input.keys
        rotate_input = (1 if pygame.K_d in keys or pygame.K_RIGHT in keys else 0) - (1 if pygame.K_a in keys or pygame.K_LEFT in keys else 0)
        thrust_input = 1 if (pygame.K_w in keys or pygame.K_UP in keys) else 0
        brake_input = 1 if (pygame.K_s in keys or pygame.K_DOWN in keys) else 0
        
        events = self.player.update(sim_dt, self.level, self.engine.time, rotate_input, thrust_input, brake_input)
        
        for ev in events:
            if ev["type"] == "dash":
                self.engine.audio.play('dash', 0.5)
            elif ev["type"] == "hit":
                self.camera.add_shake(14.0, self.engine.reduce_motion)
                self.hit_stop = 0.12
                self.damage_flash = 1.0
                self.engine.audio.play('hit', 0.8)
                if self.player.hp <= 0:
                    if self.current_checkpoint >= 0:
                        cp = self.level.checkpoints[self.current_checkpoint]
                        self.player.pos = cp[:2].copy()
                    else:
                        self.player.pos = self.level.spawn.copy()
                        self.player.angle = self.level.spawn_angle
                    self.player.hp = self.player.max_hp
                    self.player.vel = np.zeros(2, dtype=np.float32)
                    self.player.invuln = 2.0
                    self.respawn_flash = 1.0
                    self.respawn_text_timer = 1.5
                    self.engine.audio.play('checkpoint', 0.6)
            elif ev["type"] == "bounce":
                self.engine.audio.play('bounce', 0.4)
                self.camera.add_shake(min(ev["impact"] / 30, 5), self.engine.reduce_motion)
            elif ev["type"] == "wall_hit":
                pass
                
        for i, cp in enumerate(self.level.checkpoints):
            if self.checkpoint_active[i] == 0:
                if float(np.linalg.norm(self.player.pos - cp[:2])) < self.player.radius + cp[2]:
                    self.checkpoint_active[i] = 1
                    self.current_checkpoint = i
                    self.engine.audio.play('checkpoint', 0.6)
                    
        for i, orb in enumerate(self.level.orbs):
            if self.orbs_collected[i] == 0:
                if float(np.linalg.norm(self.player.pos - orb[:2])) < self.player.radius + orb[2]:
                    self.orbs_collected[i] = 1
                    self.engine.audio.play('orb', 0.5)
                    if sum(self.orbs_collected) == len(self.level.orbs):
                        self.goal_active = True
                        
        if self.goal_active:
            if float(np.linalg.norm(self.player.pos - self.level.goal)) < 25:
                self.engine.change_state("WIN", {"level_idx": self.level_idx, "time": self.level_time})
                self.level_clear_flash = 1.0
                self.engine.audio.play('win', 0.8)
                
        # Dynamic Camera Zoom
        speed = float(np.linalg.norm(self.player.vel))
        self.camera.target_zoom = 1.0 - min(0.15, speed / 3000.0)
        if self.player.dash_time > 0:
            self.camera.target_zoom = 1.1 # Zoom out slightly when dashing
            
        self.camera.update(dt, self.engine.reduce_motion)
        
        self.zone_title_timer = max(0, self.zone_title_timer - dt)
        self.respawn_text_timer = max(0, self.respawn_text_timer - dt)
        self.damage_flash = max(0, self.damage_flash - dt * 3)
        self.level_clear_flash = max(0, self.level_clear_flash - dt * 1.5)
        self.respawn_flash = max(0, self.respawn_flash - dt * 2)
        
    def draw(self):
        shader = self.engine.shader
        mesh = self.engine.mesh
        shader.use()
        
        rm = 1.0 if self.engine.reduce_motion else 0.0
        shader.set_1f("uTime", self.engine.time)
        shader.set_2f("uResolution", WIDTH, HEIGHT)
        shader.set_2f("uCamOffset", self.camera.offset[0], self.camera.offset[1])
        shader.set_1f("uZoom", self.camera.zoom)
        shader.set_1f("uReduceMotion", rm)
        shader.set_1f("uMenuMode", 0.0)
        
        self._set_scene_uniforms(self.level, self.player.pos, self.player.scale, self.player.angle,
                            self.player.radius, 1.0 - (self.player.dash_cd / 1.2),
                            1.0 if self.player.thrusting else 0.0, 1.0 if self.player.invuln > 0 else 0.0,
                            self.player.color, self.orbs_collected, self.checkpoint_active, self.goal_active)
        
        shader.set_1f("uDamageFlash", self.damage_flash)
        shader.set_1f("uLevelClearFlash", self.level_clear_flash)
        shader.set_1f("uRespawnFlash", self.respawn_flash)
        
        trail_data, trail_count = self.player.get_trail_shader_data()
        shader.set_3fv("uTrail", MAX_TRAIL, trail_data.flatten())
        shader.set_1i("uTrailCount", trail_count)
        
        mesh.draw()
        self._draw_ui()
        
    def _draw_ui(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        text = self.engine.text
        
        text.render_centered(f"ZONE {self.level_idx + 1}", WIDTH//2, 20, text.font, (255, 255, 255))
        hp_text = "  ".join(["\u2665" if i < self.player.hp else "\u2661" for i in range(self.player.max_hp)])
        text.render(hp_text, 20, 20, text.font_md, (255, 90, 110))
        
        if len(self.level.orbs) > 0:
            text.render(f"ORBS  {sum(self.orbs_collected)} / {len(self.level.orbs)}", WIDTH-160, 20, text.font, (110, 255, 190))
            
        mins = int(self.level_time // 60)
        secs = self.level_time % 60
        text.render_centered(f"{mins:01d}:{secs:05.2f}", WIDTH//2, 50, text.font_sm, (180, 180, 200))
        
        cd_frac = 1.0 - (self.player.dash_cd / 1.2)
        ready = self.player.dash_cd <= 0
        bar_w = 120; bar_h = 6; bar_x = 20; bar_y = 60
        label_col = (110, 255, 200) if ready else (180, 180, 180)
        text.render("DASH", bar_x, bar_y - 18, text.font_sm, label_col)
        text.render_quad(bar_x, bar_y, bar_w, bar_h, (40, 40, 50, 200))
        fill_w = int(bar_w * max(0.0, min(1.0, cd_frac)))
        fill_col = (110, 255, 200, 255) if ready else (180, 220, 255, 200)
        if fill_w > 0:
            text.render_quad(bar_x, bar_y, fill_w, bar_h, fill_col)
            
        if self.goal_active:
            pulse = 0.7 + 0.3 * math.sin(self.engine.time * 6)
            col = (int(255*pulse), int(90*pulse), int(140*pulse))
            text.render_centered("GOAL ACTIVE", WIDTH//2, 78, text.font, col)
            # Goal compass
            delta = self.level.goal - self.player.pos
            dist = float(np.linalg.norm(delta))
            if dist > 60:
                dir_vec = delta / dist
                arrow_pos = np.array([WIDTH//2, HEIGHT//2]) + dir_vec * 50
                ang = math.atan2(dir_vec[1], dir_vec[0])
                arrows = ["\u2192", "\u2197", "\u2191", "\u2196", "\u2190", "\u2199", "\u2193", "\u2198"]
                idx = int(((math.degrees(ang) + 22.5) % 360) / 45.0) % 8
                flip_map = {0:0, 1:3, 2:2, 3:1, 4:4, 5:7, 6:6, 7:5}
                glyph = arrows[flip_map[idx]]
                text.render_centered(glyph, int(arrow_pos[0]), int(arrow_pos[1]), text.font_md, col)
                
        if self.zone_title_timer > 0:
            fade_in = min(1.0, (3.0 - self.zone_title_timer) * 2.0)
            fade_out = min(1.0, self.zone_title_timer / 1.0)
            alpha = fade_in * fade_out
            c = int(255 * alpha)
            text.render_centered(self.level.name, WIDTH//2, HEIGHT//2 - 80, text.font_big, (c, c, c))
            sub_c = int(180 * alpha)
            text.render_centered(f"Zone {self.level_idx + 1} of {len(self.engine.levels)}",
                                      WIDTH//2, HEIGHT//2 - 30, text.font, (sub_c, sub_c, sub_c))
                                      
        if self.respawn_text_timer > 0:
            alpha = min(1.0, self.respawn_text_timer / 1.5)
            c = int(255 * alpha)
            text.render_centered("RESPAWNING", WIDTH//2, HEIGHT//2 - 40, text.font_md,
                                      (int(100*c/255), int(200*c/255), c))
                                      
        text.render_centered("A/D Rotate   W Thrust   S Brake   SPACE Dash   ESC Pause",
                                  WIDTH//2, HEIGHT - 24, text.font_sm, (130, 130, 150))
        glDisable(GL_BLEND)

class PauseState(BaseState):
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.engine.change_state("PLAYING")
            elif event.key == pygame.K_RETURN:
                self.engine.change_state("MENU")
    def draw(self):
        self.engine.states["PLAYING"].draw()
        text = self.engine.text
        text.render_quad(0, 0, WIDTH, HEIGHT, (0, 0, 0, 160))
        text.render_centered("PAUSED", WIDTH//2, HEIGHT//2 - 40, text.font_big, (255, 255, 255))
        text.render_centered("ESC to resume", WIDTH//2, HEIGHT//2 + 30, text.font, (200, 200, 220))
        text.render_centered("ENTER for Menu", WIDTH//2, HEIGHT//2 + 60, text.font, (160, 160, 180))

class WinState(BaseState):
    def enter(self, data):
        self.level_idx = data["level_idx"]
        self.time = data["time"]
        self.is_last = self.level_idx + 1 >= len(self.engine.levels)
        
        # Update Save
        level_key = str(self.level_idx)
        if level_key not in self.engine.save["best_times"] or self.time < self.engine.save["best_times"][level_key]:
            self.engine.save["best_times"][level_key] = self.time
        if not self.is_last:
            next_key = str(self.level_idx + 1)
            if next_key not in self.engine.save["unlocked"]:
                self.engine.save["unlocked"].append(next_key)
        SaveSystem.save(self.engine.save)
        
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.is_last:
                    self.engine.change_state("COMPLETE")
                else:
                    self.engine.change_state("PLAYING", {"level_idx": self.level_idx + 1})
            elif event.key == pygame.K_ESCAPE:
                self.engine.change_state("MENU")
                
    def update(self, dt):
        # Keep updating the game state underneath for visual effect
        self.engine.states["PLAYING"].update(0)
        
    def draw(self):
        self.engine.states["PLAYING"].draw()
        text = self.engine.text
        text.render_quad(0, 0, WIDTH, HEIGHT, (0, 0, 0, 120))
        text.render_centered("ZONE COMPLETE", WIDTH//2, HEIGHT//2 - 50, text.font_big, (110, 255, 190))
        mins = int(self.time // 60); secs = self.time % 60
        text.render_centered(f"Time: {mins:01d}:{secs:05.2f}", WIDTH//2, HEIGHT//2 + 10, text.font_md, (200, 220, 255))
        if not self.is_last:
            text.render_centered("ENTER for next zone", WIDTH//2, HEIGHT//2 + 70, text.font, (220, 220, 220))
        else:
            text.render_centered("ENTER to finish", WIDTH//2, HEIGHT//2 + 70, text.font, (220, 220, 220))

class CompleteState(BaseState):
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.engine.change_state("MENU")
    def draw(self):
        text = self.engine.text
        text.render_quad(0, 0, WIDTH, HEIGHT, (0, 0, 0, 180))
        text.render_centered("JOURNEY COMPLETE", WIDTH//2, HEIGHT//2 - 50, text.font_huge, (255, 215, 0))
        text.render_centered("You have traversed all zones.", WIDTH//2, HEIGHT//2 + 30, text.font_md, (220, 220, 240))
        text.render_centered("ENTER to return to menu", WIDTH//2, HEIGHT//2 + 80, text.font, (180, 180, 200))
