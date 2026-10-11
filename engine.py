import pygame
import numpy as np
from OpenGL.GL import *
from core import WIDTH, HEIGHT, FPS, Shader, Mesh, TextRenderer, AudioEngine, InputManager, SaveSystem, VERTEX_SHADER, FRAGMENT_SHADER
from states import MenuState, PlayState, PauseState, WinState, CompleteState
from levels import get_all_levels

class Engine:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.display.set_caption("THRESHOLD - A Surreal Journey")
        self.clock = pygame.time.Clock()
        
        self.shader = Shader(VERTEX_SHADER, FRAGMENT_SHADER)
        self.mesh = Mesh(np.array([
            -1.0, -1.0,  0.0, 0.0,
             1.0, -1.0,  1.0, 0.0,
            -1.0,  1.0,  0.0, 1.0,
             1.0,  1.0,  1.0, 1.0
        ], dtype=np.float32))
        
        self.text = TextRenderer()
        self.audio = AudioEngine()
        self.input = InputManager()
        self.save = SaveSystem.load()
        self.levels = get_all_levels()
        
        self.time = 0.0
        self.frame_times = []
        self.reduce_motion = False
        self.debug_overlay = False
        
        self.transition_alpha = 0.0
        self.transition_speed = 0.0
        self.next_state = None
        
        self.states = {
            "MENU": MenuState(self),
            "PLAYING": PlayState(self),
            "PAUSED": PauseState(self),
            "WIN": WinState(self),
            "COMPLETE": CompleteState(self)
        }
        self.current_state = self.states["MENU"]
        self.current_state.enter()
        
    def change_state(self, state_name, data=None):
        self.next_state = (state_name, data)
        self.transition_speed = 3.0 # Fade out in ~0.33s
        
    def run(self):
        running = True
        while running:
            raw_dt = self.clock.tick(FPS) / 1000.0
            dt = min(raw_dt, 1/30)
            self.frame_times.append(raw_dt)
            if len(self.frame_times) > 120: self.frame_times.pop(0)
            
            for e in pygame.event.get():
                if e.type == pygame.QUIT: running = False
                self.input.handle_event(e)
                
                # Global keys
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_r: self.reduce_motion = not self.reduce_motion
                    elif e.key == pygame.K_m: self.audio.toggle_mute()
                    elif e.key == pygame.K_F1: self.debug_overlay = not self.debug_overlay
                    
                self.current_state.handle_event(e)
                
            self.time += dt
            
            # Screen transition logic
            if self.transition_speed > 0:
                self.transition_alpha = min(1.0, self.transition_alpha + self.transition_speed * dt)
                if self.transition_alpha >= 1.0:
                    self.transition_speed = -3.0
                    if self.next_state:
                        state_name, data = self.next_state
                        self.current_state = self.states[state_name]
                        self.current_state.enter(data)
                        self.next_state = None
            elif self.transition_speed < 0:
                self.transition_alpha = max(0.0, self.transition_alpha + self.transition_speed * dt)
                if self.transition_alpha <= 0.0:
                    self.transition_speed = 0.0
                    
            self.current_state.update(dt)
            self.input.update()
            
            glClear(GL_COLOR_BUFFER_BIT)
            self.current_state.draw()
            
            # Draw transition fade
            if self.transition_alpha > 0.0:
                self.text.render_quad(0, 0, WIDTH, HEIGHT, (0, 0, 0, int(255 * self.transition_alpha)))
                
            # Debug Overlay
            if self.debug_overlay:
                self._draw_debug()
                
            pygame.display.flip()
        pygame.quit()
        
    def _draw_debug(self):
        avg_fps = len(self.frame_times) / max(sum(self.frame_times), 0.001) if self.frame_times else 0
        lines = [f"FPS: {avg_fps:.1f}", f"State: {self.current_state.__class__.__name__}"]
        if isinstance(self.current_state, PlayState):
            p = self.current_state.player
            lines.extend([
                f"Pos: ({p.pos[0]:.1f}, {p.pos[1]:.1f})",
                f"Vel: ({p.vel[0]:.1f}, {p.vel[1]:.1f})",
                f"HP: {p.hp}/{p.max_hp}",
                f"Dash CD: {p.dash_cd:.2f}",
                f"Zoom: {self.current_state.camera.zoom:.2f}"
            ])
        y = HEIGHT - len(lines) * 22 - 10
        for line in lines:
            self.text.render(line, WIDTH - 280, y, self.text.font_sm, (100, 255, 100))
            y += 22
