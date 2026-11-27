"""Local, bilingual shooting ideas. Product records supply subjects, never predicted results."""
from typing import NamedTuple
import re

import analytics
import reference_catalog


class Pitch(NamedTuple):
    title: str
    viewer: str
    hook: str
    first: str
    action: str
    reveal: str


# Each pitch has a visible question and an ending the creator can actually film.
# The outcome stays open until the creator runs the demonstration.
BAG = [
    (Pitch("快到闸机了，卡还在包底", "每天刷卡进站的人", "还有三步到闸机。你猜我先摸到门卡，还是那包纸巾？",
           "在家门口贴一条线当闸机，一手提早餐，门卡、钥匙和纸巾放进包里。",
           "开秒表，从线前三步开始走，到线前单手找卡。镜头留住第一次摸出来的东西。",
           "把门卡换到另一个位置再走一次，两次时间并排定格，圈出卡的位置。"),
     Pitch("Three steps to the gate and my pass is buried", "People who tap in on the way to work", "Three steps to the gate. Will I find my pass or my tissues first?",
           "Mark a gate line at home. Hold breakfast in one hand and put a pass, keys and tissues in the bag.",
           "Start a timer three steps out. Walk to the line and reach in with one hand. Keep the first thing you pull out in frame.",
           "Move the pass to a different spot and repeat. Freeze both times beside a close-up of where the pass sat.")),
    (Pitch("下班多买一本书，包里哪样得拿出来？", "下班会顺路逛书店的人", "早上刚刚好，下班多了一本书。现在得拿掉哪一样？",
           "俯拍平常带的随身物和一本书，给观众两秒猜哪样会留在桌上。",
           "先照平常的顺序装包，再把书放进去，侧拍包口和提起包的那一下。",
           "倒回桌面排出真正带走的一组，把没装进去的物件也留在画面里。"),
     Pitch("One bookshop stop on the way home", "Commuters who pick things up after work", "It all fit this morning. Does buying one book mean something has to come out?",
           "Lay out your usual carry and a book. Give viewers two seconds to pick the item that might stay behind.",
           "Pack as usual, then add the book. Film the opening from the side as you lift the bag.",
           "Lay out exactly what made it home in the bag, with anything that had to come out beside it.")),
    (Pitch("只听声音，能猜到我包里装了什么吗？", "不喜欢走路时包里叮当响的人", "闭眼听三步。你听出来，是什么在我包里打架吗？",
           "手机放在固定位置，包里装钥匙和随身物，从镜头前走过三步，先只放声音。",
           "把包倒在桌上，请观众猜是哪两样碰在一起。一次挪开一件，再走同样的三步。",
           "把声音发生变化的那两段接起来，再把当时包里剩下的东西摊给观众看。"),
     Pitch("Name what's rattling in my bag", "Walkers who notice every jingle", "Close your eyes for three steps. Can you tell what's knocking around in there?",
           "Leave the phone in one spot. Walk past with your usual carry and keys, and open with just the sound.",
           "Empty the bag on the table. Let viewers guess the noisy pair. Remove one item at a time and repeat the walk.",
           "Play the two takes where the sound changed, then reveal what was still in the bag for each.")),
]
LIGHT = [
    (Pitch("写最后一行时，谁把灯挡住了？", "晚上在小桌上写字的人", "同一盏灯，我只换一边。这行字你看哪边清楚？",
           "手机固定在本子正上方，锁定曝光，把灯摆在写字那只手旁边。",
           "慢慢抄一行字。只把灯移到桌子另一边，在下一行抄同一句。",
           "左右并排回放同一个字写到一半的瞬间，让笔尖旁的影子给出答案。"),
     Pitch("Who put a shadow on the last line?", "People who write at a small desk after dark", "Same lamp, opposite sides. Which line can you actually read while I write?",
           "Mount the phone above a notebook, lock exposure and put the lamp beside your writing hand.",
           "Copy one line slowly. Move only the lamp to the opposite side and copy the same line below.",
           "Split the frame at the same half-written word so viewers can compare the shadow at the pen tip.")),
    (Pitch("一本摊开的书，到底要占掉多少桌面？", "床边只有一张小桌的读者", "台灯、书、水杯，我想同时放下这三样。",
           "用纸胶带圈出自家床头柜的实际桌面边界，先放上灯和杯子。",
           "把书摊开翻三页，从正上方拍下每次为了翻页挪动的东西。",
           "用胶带标出最终落脚的位置，连同书翻开后的外沿一起量给镜头看。"),
     Pitch("Can my bedside table hold a whole reading session?", "Readers with one small bedside surface", "A lamp, a book and a glass of water. Can all three stay put?",
           "Mark the actual limits of your bedside table with tape. Set down the lamp and glass.",
           "Open your book and turn three pages. Film from above whenever something has to move.",
           "Mark the final positions and measure the space they take with the book still open.")),
    (Pitch("合租房里，我的书亮了，室友那边呢？", "睡前想多看两页书的室友", "这是我看到的书页。换到隔壁枕头的位置，你猜还能看到什么？",
           "在平常读书的位置打开灯，固定曝光拍下摊开的书，记下灯的朝向。",
           "把手机移到旁边枕头的高度，拍读书的人和光源，再回桌边试着换一个摆位。",
           "把两次的书页视角和枕头视角各自配成一组，让同住的人选更适合房间的一组。"),
     Pitch("My page is lit. What does my roommate see?", "Roommates who read past lights-out", "Here's the page from my seat. Guess what the same light looks like from the next pillow.",
           "Open a book where you read, switch on the lamp and lock exposure. Mark the lamp's position.",
           "Record from the neighbouring pillow at eye level, then move the lamp and repeat both views.",
           "Pair each book view with its pillow view and let your roommate pick a layout for the room.")),
]
BOTTLE = [
    (Pitch("包侧袋里，水杯和雨伞谁得让位？", "下雨也要背包通勤的人", "今天得带伞。杯子放进去以后，我还剩几只空手？",
           "把自己通勤用的包、折伞和装好水的杯子摆在门边，先给侧袋一个近景。",
           "按平常方式装包，再换一次杯子和伞的位置。两次都把包背上，单手取杯。",
           "定格两种装法下双手各拿着什么，把实际最顺手的一种留作最后一帧。"),
     Pitch("The umbrella and the bottle want the same pocket", "Backpack commuters on rainy days", "Rain today. Once the bottle is packed, how many hands do I have left?",
           "Put your usual backpack, folding umbrella and filled bottle by the door. Show the side pocket up close.",
           "Pack as usual, then swap the bottle and umbrella. Wear the bag and try taking a drink one-handed each time.",
           "Freeze both layouts with each hand in frame. End on the arrangement you actually preferred.")),
    (Pitch("我的杯子能接几杯办公室的水？", "总在开会前去接水的人", "先押个数，这一瓶能倒满几个茶水间纸杯？",
           "在同款纸杯上画相同的水位线，把写着猜测数字的便签扣在桌上。",
           "把瓶里装满的常温水依次倒到线，最后不满的一杯也摆进去。",
           "一镜拉远数杯子，翻开便签，把最后一杯的水位留在近景里。"),
     Pitch("How many office cups are in this bottle?", "People filling up before a long meeting", "Make a guess. How many break-room cups can I fill from this bottle?",
           "Mark equal fill lines on identical cups. Write your guess on a note and put it face down.",
           "Fill the bottle with room-temperature water and pour to each line. Keep the partly filled last cup.",
           "Pull back to count the cups, turn over the guess and end on the level in the last cup.")),
    (Pitch("清洗水杯，杯底那一圈到底刷到了吗？", "每天带杯子又每天洗杯子的人", "杯口看着挺宽。家里这把刷子，到了底还能转一圈吗？",
           "把空杯、常用杯刷和一张纸巾排在水槽边，先从杯口朝下拍。",
           "按平常方式把杯刷伸进去，侧拍手握的位置，再从杯口拍刷头沿杯底转一圈。",
           "取出杯刷跟杯子并排，指出这把刷子实际能碰到的位置，难拍清楚的地方也留在画面里。"),
     Pitch("Can my usual brush reach the base?", "People who wash their bottle every evening", "The opening looks wide. Can this brush still turn when it reaches the bottom?",
           "Set the empty bottle and your usual brush by the sink. Start with a view down through the opening.",
           "Insert the brush as usual. Film your grip from the side, then the brush turning from above.",
           "Lay brush and bottle side by side. Point to the areas you could reach and leave any blind spot visible.")),
]
HEADPHONES = [
    (Pitch("摘耳机赶车，我的眼镜会跟着走吗？", "戴眼镜通勤、进站时要摘耳机的人", "一只手拿着包，另一只手摘耳机。盯住我的镜腿。",
           "站在镜子前戴好眼镜和耳机，一手提包，让镜腿和耳朵同时入镜。",
           "照平时的习惯单手摘下，再从侧面慢放耳机经过镜腿的那一瞬。",
           "给眼镜原来的位置和摘完的位置各一帧，再试一次你觉得顺手的摘法。"),
     Pitch("Will my glasses come off with my headphones?", "Commuters who wear glasses", "Bag in one hand, headphones off with the other. Watch the arm of my glasses.",
           "Wear your glasses and headphones in front of a mirror. Hold your bag and frame your ear from the side.",
           "Take the headphones off one-handed as usual. Replay the moment they pass the glasses arm.",
           "Freeze the glasses before and after, then try the removal that feels most natural to you.")),
    (Pitch("视频会议前，留给耳机几秒？", "经常临时接会议的人", "会议邀请跳出来了。从桌上的耳机到听见第一声，要多久？",
           "把耳机放在平时收纳的位置，在电脑上打开自己录的一声拍手。",
           "一镜拍下取出、戴好、选中音频输出、按播放的全过程，角落放秒表。",
           "听见拍手就举手停表，回放时圈出花时间最多的那一步。"),
     Pitch("How long from the meeting invite to the first sound?", "People who jump onto calls at short notice", "Invite just landed. How long from headphones on the desk to hearing the first sound?",
           "Start with the headphones where you store them. Queue a recording of a single clap on your computer.",
           "In one take, retrieve them, put them on, select the audio output and press play beside a timer.",
           "Raise a hand when you hear the clap. Stop the clock and replay the step that took longest.")),
]
SERUM = [
    (Pitch("洗手台关灯前，瓶身上哪个字最难找？", "第一次用这瓶精华的人", "第一次用，你会先看正面，还是翻到背面找用法？",
           "把精华放在洗手台上，请朋友在没看过包装的情况下找使用说明，给手部特写。",
           "连续拍下他翻过的每一面。如果用法在外盒上，把找盒子的过程也留下。",
           "定格实际找到的那行原文并放大。没找到就把瓶身和外盒并排展示。"),
     Pitch("Where did they put the directions on this serum?", "First-time users reading the bottle at the sink", "First use. Would you look at the front or turn it over to find the directions?",
           "Put the serum by the sink. Ask a friend who has not seen the packaging to find the directions on camera.",
           "Keep every turn of the bottle in the take. If they reach for the box, follow their hands.",
           "Zoom in on the actual line they found. If it is missing, show the bottle and carton side by side.")),
    (Pitch("一滴精华，从挤出来到滑过第一格", "想在下单前看清质地的人", "先把声音关掉，你猜这滴精华会停在哪一格？",
           "把透明板放在方格纸上，滴一滴精华，手机侧拍它落下的形状。",
           "把板的一端搁在一本书上，固定机位连拍十秒，让方格和秒表同框。",
           "标出这次实际停住的格线，补拍侧面厚度，让观众自己看流动状态。"),
     Pitch("Where will one drop stop on the grid?", "Shoppers who want to see the texture", "Sound off. Which square will this drop of serum reach?",
           "Set a clear sheet over graph paper and film one drop landing from the side.",
           "Rest one end on a book. Keep the grid and a timer in frame for ten seconds.",
           "Mark where the drop actually stopped and finish on its thickness from the side.")),
]
PLANNER = [
    (Pitch("周三临时加个会，这一页还有地方写吗？", "行程常被临时打断的人", "周计划已经写满了。周三突然加个会，你会把它写哪儿？",
           "俯拍写有一周虚拟行程的手账，在周三旁贴一张写着“临时开会”的便签。",
           "把会议加进去，再把原来的安排挪走。镜头跟着笔，保留涂改痕迹。",
           "合上再翻开，请朋友用手指出改后的时间，让观众看他先找到了哪里。"),
     Pitch("It's Wednesday. Where does the surprise meeting go?", "People whose weekly plans keep moving", "The week is already full. Where would you put a surprise Wednesday meeting?",
           "Film a page filled with a fictional week. Put a note marked extra meeting next to Wednesday.",
           "Add the meeting and move the original task. Keep every crossing-out under the overhead camera.",
           "Close and reopen the planner. Ask a friend to point to the new time and show where they looked first.")),
]
LIP = [
    (Pitch("同一支唇油，门口和窗边是一个颜色吗？", "在室内挑色、出门后又想看一眼的人", "我只涂一次，从玄关走到窗边。你在哪一帧会选这个色？",
           "在手背试一笔，旁边放张白纸，固定手机的白平衡。",
           "连续从玄关走到窗边，保持同一角度，让白纸一直留在画面里。",
           "截取两个位置的静帧并排，标出各自的光源。"),
     Pitch("One swatch, two doorways", "People choosing a shade under indoor lighting", "One swatch, from the hallway to the window. Which frame would you choose the shade from?",
           "Apply one swatch to the back of your hand. Hold white paper beside it and lock white balance.",
           "Walk from the hall to the window in one take, keeping the paper and angle constant.",
           "Freeze a frame at each spot and label the two light sources side by side.")),
]
CUP = [
    (Pitch("咖啡机底下，这个杯子差几毫米？", "想带自己的杯子去接咖啡的人", "看着刚好。你猜杯沿能过咖啡机的出水口吗？",
           "从杯沿高度拍一眼自家咖啡机，给观众一秒猜间隙。",
           "在机器关闭时把空杯从正面放进去，侧面机位记录杯沿与出水口。",
           "取出杯，用尺量杯高和机器净空，同框展示这台机器的实际余量。"),
     Pitch("How many millimetres under the coffee spout?", "People bringing their own cup to the machine", "Looks close. Will the rim clear the coffee spout?",
           "Frame your coffee machine at rim height. Leave a beat to guess the clearance.",
           "With the machine off, slide the empty cup in from the front and film the gap from the side.",
           "Measure cup height and spout clearance. Show both readings for this particular machine.")),
]
STAND = [
    (Pitch("手机架好以后，视频通话里还剩半张脸吗？", "边吃午饭边跟家人视频的人", "我照平常的样子坐下。先猜对面看到的是我的脸，还是天花板？",
           "在桌上放碗和手机支架，坐回平常的位置，用前置摄像头录下第一帧。",
           "把支架挪到碗的另一侧，再试一个距离，每次拍一张屏幕里的构图。",
           "并排放三帧，在桌面贴出脸和碗都能入镜的实测位置。"),
     Pitch("Does the lunch call get my face or the ceiling?", "People catching up with family over lunch", "I'll sit down like I usually do. Guess what the other person sees first.",
           "Set a bowl and phone stand on the table. Sit normally and record the first selfie-camera frame.",
           "Move the stand across the bowl and try another distance. Save a frame from each position.",
           "Show all three crops and mark the spot that gave you your preferred view of your face and lunch.")),
]
# Broad pitches also work for products with unfamiliar names and sparse imported records.
GENERAL = [
    (Pitch("详情图里猜大小，揭晓只用一张纸", "隔着屏幕拿不准实物大小的人", "只看这一眼，你能在纸上画出它有多大吗？",
           "先拍满屏的商品近景，藏住桌沿。请朋友凭画面在纸上画下想象的轮廓。",
           "固定俯拍，把实物放在轮廓旁，沿着它真实占的地方描第二条线。",
           "挪开实物，把两条轮廓叠在一起，用尺量出猜得最偏的那一边。"),
     Pitch("Guess the size from one tightly cropped photo", "Shoppers unsure about scale on a screen", "From this close-up alone, could you draw how big it is?",
           "Crop out the table edge. Ask a friend to sketch the item's size on paper from the close-up.",
           "Switch overhead, set the item beside the sketch and trace the space it really takes.",
           "Lift the item away, overlay the two outlines and measure the side your friend missed by most.")),
    (Pitch("给它拍一张买家最想放大的照片", "收货前想看清细节的人", "你只能让我补拍一张照片。手指会停在哪里？",
           "给朋友看一张自己拍的商品全图，请他用手指点一个想放大的地方。",
           "保持手指的位置，用另一部手机贴近拍下实物对应的位置，让两张图同框。",
           "先播原图，让观众也选一次，再揭晓朋友点的部位和那张补拍的照片。"),
     Pitch("The one close-up missing from my product photo", "Shoppers who zoom in before ordering", "You get one extra photo. Where would you put your finger?",
           "Show a friend your own full-item photo. Ask them to point at the spot they want enlarged.",
           "Keep the finger there. Use a second phone for a close-up of that spot on the actual item.",
           "Show the full shot so viewers can pick a spot, then reveal your friend's choice and the new photo.")),
    (Pitch("收到货的第一分钟，手到底停在哪一步？", "第一次拿到这件商品的人", "从打开包装开始，我的手会在哪一步停下来找说明？",
           "把未打开的商品和说明放在同一桌面，手机对准双手，开始计时。",
           "按日常顺序打开并准备使用，把翻找、看说明和停顿的瞬间保留下来。",
           "回放第一次停手的画面，补拍当时在找的具体标记。如果一路顺利，就定格准备就绪的时间。"),
     Pitch("Where do my hands pause in the first minute?", "Someone opening this item for the first time", "Once I open the package, when will I first stop to look for instructions?",
           "Put the unopened item on a table. Aim the camera at both hands and start a timer.",
           "Unpack and get ready to use it as usual. Keep the reaching, reading and pauses in the shot.",
           "Replay the first pause and zoom in on the mark you were seeking. If it went smoothly, freeze the time you were ready.")),
]

STUDENT = [
    (Pitch("早八出门前，哪样东西让我回头了？", "早上赶第一节课的人", "门都关了，猜我今天回去拿什么？",
           "从门内拍下书包、课表和三个今天会用到的小物件，先盖住其中一个。",
           "照自己的早课清单收拾一遍，拿着包走到门口，把课表翻到今天。",
           "揭开那件东西，把它出现的那节课和以后放它的位置拍在同一帧。"),
     Pitch("What's sending me back before the first class?", "Students rushing to their morning class", "The door just closed. Guess what I'm going back for.",
           "Frame your bag, timetable and three things you need today. Cover one of the objects.",
           "Pack from your usual checklist, walk to the door and unfold today's timetable.",
           "Uncover the item and frame it with the class you need it for and the place you'll keep it.")),
    (Pitch("宿舍桌面只留一张 A4 纸的位置", "在宿舍小桌上写作业的人", "先别帮我收桌子，我只想找一块能摊开作业的地方。",
           "从正上方拍自己的桌子，把一张 A4 纸悬在上方让观众猜它能落在哪儿。",
           "试着放下纸，再一件一件挪动挡住它的东西，把每件的落点拍下来。",
           "摊开作业写下第一行，拉远拍原桌面和挪走的那几样。"),
     Pitch("Can I find one sheet of space on my dorm desk?", "Students doing homework on a crowded desk", "Don't tidy anything yet. Where can I put down one sheet of homework?",
           "Film the desk from above. Hold a sheet of paper over it and let viewers guess where it could land.",
           "Lower it, then move each thing in its way one at a time. Keep each new landing spot in the shot.",
           "Write the first line of homework. Pull back to show the new space and everything that moved.")),
    (Pitch("一盏灯，两个人的熄灯时间", "跟室友作息不同的学生", "我要再看两页。室友躺下以后，实际看到什么？",
           "同时拍下书页和准备休息的床位，标出两个人平常的位置。",
           "让室友从枕头高度拍一段，读书的人换个朝向再拍一段，锁定曝光。",
           "把两个视角并排，请室友点一下自己愿意留下的那个摆位。"),
     Pitch("One light, two bedtimes", "Students sharing a room on different schedules", "Two more pages for me. What does my roommate actually see from bed?",
           "Frame the book and bed and mark both people's usual positions.",
           "Record from pillow height. Turn the reader to face another way and repeat with exposure locked.",
           "Pair the two views and ask your roommate to point at the setup they would keep.")),
]

FAMILIES = (
    (r"单肩包|通勤包|托特包|帆布包|背包|手提包|双肩包|斜挎包|\b(?:shoulder bag|handbag|backpack|tote|messenger bag)s?\b", BAG),
    (r"台灯|阅读灯|书桌灯|桌灯|床头灯|\b(?:lamps?|reading lights?)\b", LIGHT),
    (r"保温杯|水杯|水瓶|运动水壶|保温壶|\b(?:water bottles?|vacuum bottles?|flasks?)\b", BOTTLE),
    (r"耳机|耳麦|\b(?:headphones?|headsets?|earbuds?|earphones?)\b", HEADPHONES),
    (r"精华液|精华露|精华|\bserums?\b", SERUM),
    (r"手账|手帐|计划本|便签本|日程本|\bplanners?\b", PLANNER),
    (r"唇油|唇釉|唇彩|\blip (?:oils?|glazes?|gloss)\b", LIP),
    (r"马克杯|咖啡杯|陶瓷杯|\b(?:ceramic cups?|coffee cups?|mugs?)\b", CUP),
    (r"手机支架|\bphone stands?\b", STAND),
)

# Both languages of a story share the same editorial references and shot adaptations.
REFERENCE_TOPICS = {
    pitch: key for family, keys in (
        (BAG, ("bag-pass", "bag-book", "bag-sound")),
        (LIGHT, ("lamp-shadow", "lamp-desk", "lamp-room")),
        (BOTTLE, ("bottle-pocket", "bottle-pour", "bottle-brush")),
    ) for pair, key in zip(family, keys, strict=True) for pitch in pair
}


def pitches_for(subject, english=False, *, include_scenes=False):
    matches = [(match.start(), pitches) for pattern, pitches in FAMILIES
               if (match := re.search(pattern, subject, re.I))]
    specific = min(matches, key=lambda item: item[0])[1] if matches else []
    if not specific and include_scenes and re.search(r"宿舍|学生|早八|\b(?:dorm|student)s?\b", subject, re.I):
        specific = STUDENT
    return [pair[int(english)] for pair in (specific + GENERAL)[:3]]


def shooting_text(pitch, english):
    labels = ("For", "Opening line", "First frame", "Next shot", "Final frame") if english else (
        "拍给谁看", "开场口播", "第一镜", "接着拍", "收尾画面")
    return "\n".join([pitch.title, *(f"{label} · {value}" for label, value in zip(labels, pitch[1:]))])


def board(db, params):
    scope = analytics.scope_for(db, params)
    ranked = analytics.ranking_page(db, scope, {"kind": "products", "limit": 20})["items"]
    products = [{key: row[key] for key in ("id", "name", "kind", "image_key")} for row in ranked]
    subject = params.get("subject", "").strip()
    if len(subject) > 1500:
        raise ValueError("商品名称过长")
    product = None
    product_id = params.get("product_id")
    if product_id:
        row = db.execute("""SELECT id,name,kind,image_key FROM analytics_daily
            WHERE source=:source AND market=:market AND kind='products' AND id=:product_id
              AND date BETWEEN :start_date AND :date ORDER BY date DESC LIMIT 1""", {**scope, "product_id": product_id}).fetchone()
        if row is None:
            raise LookupError("当前市场和时间范围内没有此商品")
        product = dict(row)
        subject = product["name"]
    elif subject:
        # Existing name-only bookmarks can identify a product only when its latest name is unique.
        matches = db.execute("""SELECT d.id,d.name,d.kind,d.image_key FROM analytics_daily d
            WHERE d.source=:source AND d.market=:market AND d.kind='products' AND d.name=:subject
              AND d.date BETWEEN :start_date AND :date AND NOT EXISTS(
                SELECT 1 FROM analytics_daily s WHERE s.source=d.source AND s.market=d.market
                  AND s.kind=d.kind AND s.id=d.id AND s.date>d.date AND s.date<=:date)
            LIMIT 2""", {**scope, "subject": subject}).fetchall()
        if len(matches) == 1:
            product = dict(matches[0])
    english = params.get("locale") == "en-US"
    cards = []
    reviewed, library = reference_catalog.references()
    result = {**scope, "products": products, "product": product, "subject": subject, "cards": cards,
              "linked_videos": analytics.product_video_links(db,scope,"products",product["id"]) if product else [],
              "references_reviewed": reviewed}

    def add(name, product, pitch):
        topic = REFERENCE_TOPICS.get(pitch)
        cards.append({"subject": name, "product": product, **pitch._asdict(), "topic": topic,
                      "references": library.get(topic, [])})

    if subject:
        for pitch in pitches_for(subject, english):
            add(subject, product, pitch)
    elif products:
        # Lead with different product stories before filling spare slots with other angles.
        candidates = [(p, pitches_for(p["name"], english)) for p in products]
        seen = set()
        for position in range(3):
            for product, pitches in candidates:
                pitch = pitches[position]
                if pitch.title not in seen:
                    seen.add(pitch.title)
                    add(product["name"], product, pitch)
                if len(cards) == 3:
                    return result
    return result
