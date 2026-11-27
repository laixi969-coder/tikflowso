// Replacements are specific to the selected story. Home sets the scene, solo changes
// the camera work, and a faceless cut opens on a caption and ends on physical evidence.
const treatments = {
  'bag-pass': {
    home: ['把玄关钥匙盘当读卡器，在三步外贴起点线。门卡塞进包，另一只手提面包，手机靠在鞋柜上拍包口。', 'Use a key tray as the reader and tape a start line three steps away. Bury the pass, hold a bread bag and prop the phone on the shoe cabinet facing the bag opening.'],
    solo: ['固定手机，按下录像再走进画面。每次从同一个地面标记出发，单手摸卡。回放时用卡完全露出包口的那一帧停表。', 'Fix the phone in place and walk into frame after pressing record. Start on the same floor mark each time and time both takes to the frame where the entire pass clears the bag.'],
    faceless: ['只留包口、门卡和两只手，把两次最先掏出来的物件并排放在卡旁，叠上各自用时。', 'Crop to the bag opening, pass and hands. Lay the first object from each attempt beside the pass and overlay both times.'],
    caption: ['还有三步。先摸到门卡，还是纸巾？', 'Three steps left. Pass or tissues first?'],
  },
  'bag-book': {
    home: ['餐桌上铺好平常带的东西。从家里书架取一本平装书，先把它留在画面外。', 'Lay your usual carry on the kitchen table. Take one paperback from your shelf and leave it just out of frame.'],
    solo: ['手机靠一摞书固定在包口高度。一镜拍下自己装包、把书推进去、试着合上包口，再单手提起的过程。', 'Prop the phone on books at the height of the bag opening. Film yourself packing, adding the book, trying the closure and lifting the bag, all in one take.'],
    faceless: ['俯拍双手把装进去的东西摆进纸胶带框，把留在包外的放在框外。最后一本书停在它实际归属的那一边。', 'Film your hands from above. Put what fit inside a tape outline and the leftovers outside. Leave the book on the side where it actually belongs.'],
    caption: ['下班多买一本书，谁得让位？', 'I bought one book. What has to come out?'],
  },
  'bag-sound': {
    home: ['用玄关到客厅的三块地砖当路线。把钥匙、硬币和随身物装进包，关掉电视，先录一遍脚步声。', 'Mark a three-tile route from the hall. Load the bag with keys, coins and everyday items, turn the TV off and record the footsteps.'],
    solo: ['手机放在路线中点，连续录像。每次在镜头前取出一件、走同样的三步，再回来把那件放在地上作标记。', 'Set the phone halfway along the route and keep it rolling. Remove one object on camera, walk the same three steps and leave the object on the floor as a marker.'],
    faceless: ['镜头朝下只拍鞋尖和包。连续播放声音有变化的两段，最后用手把对应物件推进同一画面。', 'Aim down at your shoes and bag. Play the two takes where the sound changed, then slide the objects into frame with your hand.'],
    caption: ['先听。包里是哪两样东西在响？', 'Listen first. Which two things are rattling?'],
  },
  'lamp-shadow': {
    home: ['在餐桌放一张写了两行格子的纸，用两张便签标出灯可以放的左右位置，关掉会变化的屏幕光。', 'Draw two writing lines on paper at the kitchen table. Mark left and right lamp positions with sticky notes and turn off changing screen light.'],
    solo: ['把手机固定在不会挡光的位置并锁曝光，一次录完。左边抄一行，只挪灯，再抄一行，写到同一个字时都停一拍。', 'Fix the phone outside the light path and lock exposure. Record continuously. Copy a line, move only the lamp and repeat, pausing on the same letter.'],
    faceless: ['截取两个笔尖停顿的瞬间，把纸页、手指和影子并排放大，手指点出影子有没有压到字。', 'Freeze both pen pauses. Enlarge only the page, fingers and shadows side by side and point out whether the shadow crosses the writing.'],
    caption: ['只挪一盏灯。哪一行被手挡住了？', 'Only the lamp moves. Which line falls in shadow?'],
  },
  'lamp-desk': {
    home: ['把家里的小边桌当床头柜，沿桌边贴纸胶带，把自己睡前真会用的灯、书和空杯放在桌旁。', 'Use a small side table at home. Tape its edges and set out the lamp, book and empty glass you would actually use before bed.'],
    solo: ['把手机靠在书架上斜俯拍，全程双手可用。摊书翻三页，每挪一次灯或杯子，就在原位留一张便签。', 'Prop the phone on a shelf for an angled overhead view. Turn three pages and leave a sticky note at every spot where the lamp or glass had to move.'],
    faceless: ['俯拍桌沿，手拿尺量摊开的书到杯底的空隙，最后把尺放下，让整张桌面的真实占位留在画面里。', 'Crop to the tabletop. Measure between the open book and the glass, then put down the ruler and show the entire usable surface.'],
    caption: ['灯、书、水杯，翻一页要挪几个？', 'Lamp, book, glass. What moves when I turn a page?'],
  },
  'lamp-room': {
    home: ['在卧室摊开一本书，隔壁枕头的位置放一把椅子，椅背搭条毛巾标出另一人的眼睛高度。', 'Open a book in your bedroom. Put a chair where the next pillow would be and mark eye level with a towel on the chair.'],
    solo: ['在书页旁和枕头高度各做一个手机定位点，锁曝光。先后从两点各录三秒，挪灯后再走一遍，全程自己换机位。', 'Mark two phone positions at the book and at pillow height. Lock exposure and film three seconds from each. Move the lamp, then repeat the two angles yourself.'],
    faceless: ['并排放书页特写和枕头视角的灯面，遮住画面外反光中的脸，用 A、B 标出两种摆法。', 'Pair a page close-up with the light as seen from pillow height. Crop any reflections of faces and label the arrangements A and B.'],
    caption: ['我在看书。隔壁枕头看到的光是哪一束？', 'I see the page. What light reaches the next pillow?'],
  },
  'bottle-pocket': {
    home: ['把背包挂在玄关椅背，带水的杯子和折伞放在门口的鞋盒上。鞋盒边缘与侧袋口一起入镜。', 'Hang the backpack on a hallway chair. Put the filled bottle and umbrella on a shoebox by the door and frame it with the side pocket.'],
    solo: ['固定手机在腰高，用胶带标好站位。背上包，对着同一机位先从一侧抽杯，再调换杯伞位置重复。', 'Fix the phone at waist height and tape a standing mark. Wear the pack, draw the bottle, swap it with the umbrella and repeat on the same mark.'],
    faceless: ['截取两次取杯完毕的腰部以下画面，定格杯和伞分别落在哪只手里。', 'Crop both finished takes below the waist and freeze which hand ended up holding the bottle and the umbrella.'],
    caption: ['下雨了。杯子和伞，哪个能单手拿到？', 'Rain today. Which one can I reach one-handed?'],
  },
  'bottle-pour': {
    home: ['厨房台面排一排同款小杯，用胶带画齐水位。在杯前扣一张写了猜测数字的纸条，装满自己的水瓶。', 'Line up matching cups on the kitchen counter and tape the same fill line on each. Hide your guess on a slip and fill your own bottle.'],
    solo: ['手机靠稳在水位线高度，一手依次倒水，另一手把倒到线的杯子推向镜头。最后不足一杯时也不停机。', 'Prop the phone at fill-line height. Pour with one hand and slide each filled cup toward the lens with the other. Keep recording the partly filled final cup.'],
    faceless: ['只拍杯壁和手，依次给满杯推入数字纸签。最后揭开猜测纸条，给未满那杯的水线一个近景。', 'Show only cups and hands. Slide a number in front of each full cup, uncover your guess and finish on the water line in the last cup.'],
    caption: ['一整瓶，能倒满几杯？先猜个数。', 'How many full cups in this bottle? Make a guess.'],
  },
  'bottle-brush': {
    home: ['在自家水槽边铺毛巾防滑，把平常洗杯子的刷子贴着杯壁摆好，先拍刷头与杯底的高度差。', 'Lay a towel by your sink. Set your usual brush against the bottle and film the height difference between the bristles and the base.'],
    solo: ['把手机固定在水槽边上方。左手稳住杯子，右手把刷子伸到底，手指在杯口高度捏住刷柄再抽出。', 'Fix the phone just above the sink. Steady the bottle, lower the brush, pinch the handle at the rim and withdraw it without moving your grip.'],
    faceless: ['从侧面只拍双手，用手指捏住或用胶带标出实际伸入的长度，和杯子并排。看不到的内角也保留在画面中。', 'Frame only your hands from the side. Pinch or tape the insertion depth and compare it beside the bottle. Leave any hidden corners visible as blind spots.'],
    caption: ['杯口过得去，刷头够得到底吗？', 'Through the opening. But can the brush reach the base?'],
  },
};

export const conditionLabels = {solo:'一个人拍', home:'在家拍', faceless:'不露脸'};

export function referenceDraft(row, english) {
  const name = row.subject;
  const is = pattern => pattern.test(row.title);
  let lines;
  if (is(/unbox|开箱|拆箱/i)) {
    lines = english
      ? ['From the sealed box to the first use', 'What is the first thing I need that is missing from this box?', 'Frame the sealed box and an empty spot for everything inside.', 'Unpack in order. Keep the camera rolling as you try the first step in the instructions.', 'Lay what came in the box beside anything you had to get separately.']
      : ['从拆封拍到第一次用上', '只靠这一盒东西，第一步就能用起来吗？', '把未拆的包装放在桌边，旁边留一块空位，拍清封口。', '按取出顺序把东西放进空位，照说明试用第一步，缺什么就把寻找过程留下。', '把盒内自带的和自己补拿的分两边摆好，定格第一次用上的画面。'];
  } else if (is(/\bvs\b|versus|compar|对比|横评/i)) {
    lines = english
      ? ['Put two ways of using it side by side', 'Which way would you pick after watching the same task twice?', 'Mark two positions, A and B. State the one thing you will change.', 'Film the same task twice at the same distance, changing only the thing on the label.', 'Freeze both takes on the same step and point to one visible difference.']
      : ['同一件事拍两遍，让观众自己选', '两种用法，只改一个条件，你会选哪边？', '写下 A、B 两张纸条，在每张上写清这一次要改的条件。', '同一机位、同一项操作各拍一遍，每次只改纸条上的那一项。', '定格在操作的同一步，左右并排，手指点出实际看得到的差别。'];
  } else if (is(/tutorial|how to|setup|教程|安装/i)) {
    lines = english
      ? ['Show the step a first-time user might miss', 'Could you repeat this step if I covered the instructions?', 'Show the finished setup for one second, then return to the starting position.', 'Film the step slowly. Pause just before the part that needs a closer look.', 'Repeat it once at normal speed with the crucial detail visible.']
      : ['把新手容易漏的一步单独拍清楚', '挡住说明书，这一步你能一次做对吗？', '先给完成状态一秒，再把商品放回开始的位置。', '慢慢做一遍，在最需要看清的地方停一下，补一帧手部特写。', '用正常速度再做一次，把刚才放大的细节留在画面里。'];
  } else {
    lines = english
      ? ['Test one detail before buying', 'What would you want to see once before paying for this?', 'Write one question from the reference title on a note and place it beside your product.', 'Try one everyday task that answers that question. Film the full attempt, including any pause or second try.', 'Replay the frame that answers the note and give the result for your own item.']
      : ['挑一个下单前最想看清的细节', '下单前只能亲手试一次，你先试哪里？', '从原片标题挑一个自己也在意的问题，写在便签上，放在商品旁。', '找一个日常动作来验证它，完整拍一遍，把停顿和重试也留下。', '把能回答便签问题的那一帧停住，说出自己这件商品的实际表现。'];
  }
  return {subject:name, topic:row.url, title:name + ' · ' + lines[0], viewer:english ? 'Someone considering this product' : '正在考虑这件商品的人',
    hook:lines[1], first:lines[2], action:lines[3], reveal:lines[4], references:[row]};
}

export function adaptIdea(idea, selected, english) {
  const treatment = treatments[idea.topic];
  const draft = {...idea};
  if (!treatment) {
    if (selected.includes('home')) draft.first = (english ? 'At home, clear a spot near a window. ' : '在家里窗边腾出一小块位置，用自然光。') + draft.first;
    if (selected.includes('solo')) draft.action = (english ? 'Prop your phone on books and mark the product position with tape. Start recording before you reach into frame. ' : '把手机靠在书堆上，用胶带标出商品的位置。先按录像，再伸手进画面。') + draft.action;
    if (selected.includes('faceless')) draft.reveal = (english ? 'Frame only your hands and the product. ' : '裁到只剩双手和商品，把结论打在画面下方。') + draft.reveal;
    return draft;
  }
  const i = english ? 1 : 0;
  if (selected.includes('home')) draft.first = treatment.home[i];
  if (selected.includes('solo')) {
    draft.action = treatment.solo[i];
    if (idea.topic === 'lamp-room') draft.reveal = english
      ? 'Pair the two page views with their pillow views and label which setup you would use tonight.'
      : '把两次书页和枕头视角各配成一组，自己选出今晚愿意用的摆法。';
  }
  if (selected.includes('faceless')) {
    draft.hook = treatment.caption[i];
    draft.reveal = treatment.faceless[i];
    if (idea.topic === 'lamp-room' && !selected.includes('solo')) draft.action = english
      ? 'Shoot from just above the pillow toward the light, keeping both people out of frame. Turn the lamp toward the book and repeat from the same pillow seam.'
      : '从枕头边缘朝灯面拍，构图里只留灯和书。把灯转向书页，再从枕套同一条缝的位置拍一次。';
  }
  return draft;
}

export function renderReferences(rows, english, esc) {
  if (!rows?.length) return '';
  const item = row => '<div class="idea-reference"><a data-source-text target="_blank" rel="noopener noreferrer" href="' + esc(row.url) + '">' +
    esc(row.title) + ' ↗</a><small data-source-text>' + esc((row.platform === '抖音' && english ? 'Douyin' : row.platform) + ' · ' + row.author) +
    '</small><p>' + esc(english ? row.en : row.zh) + '</p><small>' + (english ? 'Published ' : '发布 ') + esc(row.published) +
    (english ? ' · Added ' : ' · 收录 ') + esc(row.added) + '</small></div>';
  return '<section class="idea-references"><h4>' + (english ? 'Reference video' : '参考原片') + '</h4>' + item(rows[0]) +
    (rows.length > 1 ? '<details><summary>' + (english ? 'More references' : '更多参考') + ' (' + (rows.length - 1) + ')</summary>' +
      rows.slice(1).map(item).join('') + '</details>' : '') + '</section>';
}
