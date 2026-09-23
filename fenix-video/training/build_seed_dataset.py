# بيانات أولية (seed) لعقل Fenix Video — مؤلّفة يدويًا حسب مخطط /api/video/script بالضبط.
# كل مثال يُتحقق منه بـ parse_script() قبل الحفظ — الصيغة مضمونة 100%.
# لاحقاً: fenix-video/training/gen_dataset.py يضيف أمثلة من العقل الحي فوق هذه القاعدة.
#
#   python fenix-video/training/build_seed_dataset.py
#
# الناتج: fenix-video/training/data.jsonl (seed + أي أمثلة حية سابقة إذا وُجدت في data_live.jsonl)
import importlib.util
import json
from pathlib import Path

_here = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("fenix_video_brain", _here.parent / "api" / "brain.py")
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)

# (الأسلوب، اللغة، الفكرة، العنوان، [(visual EN، vo باللغة، secs)، ...])
SEED = [
    ("cinematic, moody, neon", "Darija/Arabic", "مطاردة ليلية على الكورنيش فالدار البيضاء",
     "ليل الكورنيش", [
         ("Night aerial of the Casablanca corniche, wet asphalt reflecting purple neon, one car weaving through empty lanes, cinematic moody grade", "الكورنيش فالليل، والمدينة كاملة قدامنا.", 6),
         ("Interior car shot, hands gripping the wheel, dashboard glow on a focused face, city lights streaking past the window", "القاعدة بسيطة: ماتشوفش الضوء الأحمر.", 5),
         ("Low angle tracking shot of tires slicing through rain puddles, spray exploding in slow motion under streetlights", "المطر صار موسيقى، والمحرك الإيقاع.", 6),
         ("Wide shot: the car drifts around a seaside roundabout, lighthouse beam sweeping across the frame, neon reflections dancing", "اللفة الأخيرة قبل البحر.", 5),
         ("Car stops at the pier edge, brake lights bleeding red into wet ground, driver steps out silhouette against the Atlantic", "وصطى الليل، البحر هو المحكمة.", 6),
     ]),
    ("cinematic, golden hour", "Darija/Arabic", "صعود فنان من الحومة للمسرح",
     "من الحومة للضو", [
         ("Golden hour over a cramped medina rooftop, young rapper scribbling rhymes in a worn notebook, laundry lines and satellite dishes around", "كل كلام كتبتو هنا، فالسطح.", 6),
         ("Close-up of cracked sneakers climbing steep stairs, warm sunset light cutting through narrow alley shadows", "الدرج طويل، ولكن الحلم أطول.", 5),
         ("Backstage mirror lit by a single bulb, artist breathing slowly, mic tape wrapped around fingers, crowd rumble beyond the curtain", "خلف الكواليس، القلب كيدق بزاف.", 5),
         ("Slow push-in from behind: silhouette steps into blinding stage lights, sea of raised hands in haze", "ومن هادي... كتبدا الحكاية الحقيقية.", 6),
     ]),
    ("dark, rainy, neon-noir", "Arabic", "محقق يتبع أدلة في مدينة مطرة",
     "أثر المطر", [
         ("Rain-drenched neon alley, detective in long coat crouches over a glowing clue, reflections trembling in black puddles, noir palette", "المطر يمسح كل شي... إلا الأثر.", 6),
         ("Extreme close-up: a burned match and a torn photo held with tweezers, evidence bag light, rain drumming on tin roof", "علامة تجارية، وصبغة من الورق.", 5),
         ("Detective's face lit by a flickering bar sign, smoking figure watching from a window above, vertical neon streaks", "المشكوك فيه فوق، وأنا تحت.", 5),
         ("Rooftop confrontation in heavy rain, two silhouettes facing, city grid glittering below like a circuit board", "المدينة كلها شهود، وماحد يشهد.", 6),
     ]),
    ("uplifting, sunrise, drone", "Arabic", "رحلة صباحية في جبال الأطلس",
     "فجر الأطلس", [
         ("Drone rises over terraced Atlas mountain village at dawn, mist pooling in valleys, first light touching snow peaks", "قبل ما تصحى المدينة، الجبال صحت.", 6),
         ("Shepherd silhouette walking a ridge line, breath visible in cold air, sun cresting the peak behind him", "خطوة بخطوة، والسماء كلها لي.", 5),
         ("Close-up of mint tea poured into a glass, steam curling in golden light, weathered hands steady", "أتاي فالفجر طعمو مختلف.", 5),
         ("Wide drone shot: trail switchbacking down to a green oasis, birds crossing frame, day fully arriving", "الطريق طويل، ولكن السماء صافية.", 6),
     ]),
    ("high-energy, street, handheld", "Darija/Arabic", "ليلة مباراة والشوارع مشتعلة",
     "ليلة الماتش", [
         ("Handheld rush through a packed fan zone, flares smoking red, flags snapping, faces painted, chaotic energy", "البلاد كاملة في زنقة وحدة الليلة.", 6),
         ("Slow motion: goal on a big screen, hundred heads snap back screaming, drinks flying, strobe of phone lights", "گول! والدنيا هزات.", 5),
         ("Street cascade: crowd floods onto the boulevard, honking cars, someone waves a giant flag from a moving bus", "الشارع ولا الملاعب.", 5),
         ("Dawn aftermath: empty square littered with scarves, street sweeper smiles, sunrise over the stadium arch", "وصباحها... البطولة باقية فالقلب.", 6),
     ]),
    ("cinematic, moody, neon", "English", "a heist crew walks into a midnight casino",
     "Midnight Mirage", [
         ("Rain-slick casino entrance at midnight, neon signage bleeding into puddles, four silhouettes in tailored coats step through golden doors", "At midnight, the house always wins — usually.", 6),
         ("Interior: chandelier glare, slow-motion roulette spin, dealer's eyes tracking the crew as they split across the floor", "Four players, one table, zero mistakes allowed.", 5),
         ("Extreme close-up: a card palmed, a camera lens rotating away on its own, a bartender sliding a key across mahogany", "Every eye is a lock. We brought the keys.", 5),
         ("Vault door swings open, stacks glowing under red light, crew exchanges a single nod as alarms silently arm", "Ten seconds of red light. Then silence.", 6),
     ]),
    ("warm, nostalgic, 35mm film", "English", "the last summer before everything changed",
     "The Last July", [
         ("35mm grain: kids leaping off a lake dock at sunset, lens flare, film scratches, endless golden water", "That summer, the water was always warm.", 6),
         ("Polaroid photo taped to a bedroom mirror, four laughing faces, sunlight crawling across the wallpaper", "We took one photo. We thought there'd be thousands.", 5),
         ("Two friends on a car hood at dusk, radio glowing, sharing earbuds, fireflies starting over the fields", "One song on repeat. No reason to move.", 5),
         ("Empty dock at dawn, a single bike lying on its side, lake perfectly still", "September came. The dock remembers.", 6),
     ]),
    ("epic, orchestral, aerial", "English", "a lone climber conquers a frozen peak",
     "The Summit", [
         ("Aerial: a lone climber traverses a knife-edge ridge, clouds racing below, sun flaring off ice axes", "Six thousand meters. One line upward.", 6),
         ("Macro: ice crystals forming on an oxygen mask, breath fogging, gloved fingers trembling on carabiners", "The mountain doesn't care. That's why we climb.", 5),
         ("Wide: storm wall approaching, climber anchors in and holds as white fury engulf the frame", "Hold. Breathe. Hold.", 5),
         ("Sunrise summit: climber stands above an ocean of clouds, flag planted, orchestra swelling, horizon burning gold", "Above the clouds, the world finally fits.", 6),
     ]),
    ("fast-paced, glitchy, cyberpunk", "English", "a courier races through a neon megacity",
     "Neon Run", [
         ("Cyberpunk megacity canyon, hover-drones scanning, courier on a glowing bike weaving through holographic traffic at insane speed", "Package. Thirty minutes. The whole city between us.", 6),
         ("Glitch transition: courier's HUD zooms — route flickering through eight alleys, drone net tightening, countdown burning red", "Drones ahead. Walls behind. One road left.", 5),
         ("Wheel cam: bike leaping a canal gap in slow motion, sparks raining, holo-ads shattering like glass", "Sometimes the shortcut is a leap of faith.", 5),
         ("Rooftop skid to a stop, hand-off of a glowing case to a hooded figure, city grid glittering below", "Delivered. Never ask what was inside.", 6),
     ]),
    ("documentary, natural light", "French", "un matin au marché de Marseille",
     "Le Marché", [
         ("Documentary style: dawn light on the Vieux-Port, fishermen unloading crates, gulls swirling, harbor bells", "Marseille se réveille avec la mer.", 6),
         ("Market stall close-ups: hands stacking oranges, weathered smile, price chalk squeaking on a slate", "Ici, chaque fruit a une histoire.", 5),
         ("Tracking shot: an old regular greets three vendors in a row, bread under one arm, gossip in the air", "Le marché, c'est le parlement du quartier.", 5),
         ("Wide golden shot: crowded stalls under awnings, sun climbing, laughter over the fish scale clatter", "À midi, tout le monde repart avec plus que des courses.", 6),
     ]),
    ("dreamy, pastel, slow-motion", "Spanish", "un verano infinito en la costa",
     "Verano Infinito", [
         ("Pastel slow motion: kids running through a sprinkler at dusk, water droplets like glass beads, lavender sky", "El verano no terminaba nunca.", 6),
         ("Super 8 look: a girl's hair lifting in the sea breeze on a boardwalk, candy colors, gentle lens flare", "Y el mar guardaba todos los secretos.", 5),
         ("Underwater shot: sunlight rays through turquoise, laughing faces looking down from the surface", "Debajo del agua, el tiempo iba más lento.", 5),
         ("Empty beach at golden hour, one towel, one pair of sandals, waves erasing footprints", "Nos fuimos. El verano se quedó.", 6),
     ]),
    ("anime-inspired, vivid, dynamic", "Japanese", "放課後の屋上での決闘",
     "屋上の約束", [
         ("Anime style: after-school rooftop at sunset, two students facing off, wind lifting uniforms, city skyline blazing orange", "放課後、屋上。約束通りだ。", 6),
         ("Dynamic speed lines: a wooden sword drawn in a flash, cherry petals spiraling, eyes narrowing in close-up", "一度だけ、本気で行く。", 5),
         ("Slow motion clash: blades crossing, shockwave rippling the clouds above, pupils locking", "全力じゃなきゃ、失礼だからな。", 5),
         ("Both laughing on the fence at dusk, graduation clouds rolling past, sunset bleeding into purple", "……勝負は、まだ続くな。", 6),
     ]),
    ("moody, snowy, minimalist", "Russian", "ночная поездка по заснеженному городу",
     "Снежный маршрут", [
         ("Minimalist night: a tram glides through falling snow, warm windows glowing, frozen city hushed and white", "Ночь. Город спит под снегом.", 6),
         ("Inside the tram: breath fogging the glass, a passenger draws a small bird in the frost with one finger", "На стекле — птица, которая не улетит.", 5),
         ("Snow crunch underfoot crossing an empty square, lamplight halos, cathedral silhouette behind flakes", "Тишина, в которой слышно себя.", 5),
         ("Tram recedes into the white distance, tracks vanishing under fresh snow, one lit window remains", "Утром снег всё скроет. Но не забудет.", 6),
     ]),
    ("luxurious, sleek, product-ad", "English", "launch night of the Fenix flagship phone",
     "Fenix One — Launch Night", [
         ("Sleek product-ad: black glass tower wrapped in purple light beams, gold confetti freezing mid-air, Fenix One logo reveal", "Tonight, Fenix changes everything.", 6),
         ("Macro beauty shot: titanium edge rotating, camera lenses blooming open like an iris, reflections sliding across glass", "Precision you can feel before you touch it.", 5),
         ("Crowd: phone screens lighting up in waves across a dark auditorium, faces glowing, countdown hitting zero", "Ten thousand hands. One device.", 5),
         ("Hero shot: the phone standing upright on a pedestal, purple and gold light wrapping around it, city lights beyond the glass", "Fenix One. The night belongs to you.", 6),
     ]),
    ("cozy, warm, lo-fi vibes", "English", "3am coding session that becomes a breakthrough",
     "3AM", [
         ("Lo-fi cozy: dark room lit by monitor glow, coffee steam rising, cat asleep on a hoodie, code scrolling softly", "3AM. The bug knows it's cornered.", 6),
         ("Close-up: tired eyes reflecting green terminal text, fingers hovering, rain starting against the window", "One more try. That's what the last fifty said.", 5),
         ("Screen floods green — tests passing one by one, fists slowly rising, chair spinning back in disbelief", "It builds. IT BUILDS.", 5),
         ("Sunrise creeps over the windowsill onto the keyboard, head finally resting on folded arms, cat relocates to shoulder", "Shipped by sunrise. Legend by lunch.", 6),
     ]),
]


def main():
    rows = []
    for style, language, topic, title, scenes in SEED:
        system = vb.script_system(language, style, topic)
        user = f"Write the video script JSON for: {topic}."
        payload = {"title": title, "scenes": [
            {"n": i + 1, "visual": v, "vo": vo, "secs": s}
            for i, (v, vo, s) in enumerate(scenes)
        ]}
        # تحقق صارم: نفس المدقق الذي يفحص ردود العقل وقت التشغيل
        vb.parse_script(json.dumps(payload, ensure_ascii=False))
        rows.append({"messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        ]})
        print(f"  ✓ {title} ({len(scenes)} scenes, {sum(s['secs'] for s in payload['scenes'])}s)")

    out = _here / "data.jsonl"
    live = _here / "data_live.jsonl"  # أمثلة من العقل الحي إن وُجدت — تُدمج فوق الـ seed
    if live.exists():
        for line in live.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        print(f"  + merged {len(rows) - len(SEED)} live examples")

    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"✅ {len(rows)} examples → {out}")


if __name__ == "__main__":
    main()
