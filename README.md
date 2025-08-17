# 🕹 Old-School Pinball Game (Python + Pygame)

A fully playable, GUI‑based pinball game built with **Python** and **Pygame**.  
Includes flippers, bumpers, a plunger launch, scoring, lives, and a simple HUD — all wrapped in a classic arcade feel.

---

## 🎮 Features

- **Physics Engine:**  
  Gravity, bouncy collisions, simple friction, and flipper impulse.
- **Flippers:**  
  Left & right, angle‑limited, animated rotation.
- **Plunger Launch:**  
  Charge with Spacebar and release to send the ball flying.
- **Bumpers:**  
  Score‑boosting targets with extra bounce.
- **Table Layout:**  
  Side walls, drain, and safe ball relaunch after loss.
- **HUD:**  
  Score, high score, balls left, pause indicator, and game over prompt.
- **Controls:**  
  - **Left Flipper:** `Left Arrow` or `Z`  
  - **Right Flipper:** `Right Arrow` or `/`  
  - **Plunger:** Hold `Space` to charge, release to launch  
  - **Pause:** `P`  
  - **Restart:** `R` after Game Over  
  - **Quit:** `ESC`

---

## 🛠 Installation & Setup

### 1. Clone the repo
```bash
git clone https://github.com/YourUsername/Pinball-game.git
cd Pinball-game
```

### 2. Install requirements
```bash
pip install -r requirements.txt
```

### 3. Run the game
```bash
python pinball.py
```

---

## ⚙️ Customization
You can tweak gameplay feel in the code:

1. Variable	Effect
2. GRAVITY	Higher = faster ball drop; lower = floatier
3. RESTI_BALL_WALL	Bounciness off walls
4. TANGENTIAL_FRICTION	Ball slowing on wall impact
5. RESTI_BALL_BUMPER	Bounciness off bumpers

---

## 📂 Project Structure
Code
Pinball-game/
│
├── pinball.py      # Main game script
├── README.md       # This file
└── requirements.txt 


## 🎯 Next Steps & Ideas
Add slingshots, rollover lanes, and more obstacles

Implement sound effects & music with pygame.mixer

Multi‑ball mode and score multipliers

Improve flipper physics for more realism

