import discord
from discord.ext import commands, tasks
import random
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== 設定 =====
CHANNEL_IDS = [1501413828980899911]
ROLE_ID = 1501220776420835388

# ===== 路線データ（例）=====
lines_data = {
    "涼邨山鉄道涼邨本線": ["夏海","北夏海","涼邨さんごの杜","トロピカる海岸","南振原","振原","東振原","烏橋海岸","雪城本町","馬渡降","実卿","見手稲","美澄","大野","春野","所流野","段野","矢野","風野","厳野","厳野学園","南本古原","本古原","南涼邨","涼邨","涼邨学園","馬原","月影学園","明堂学園","南花咲","花咲岬","花山大橋","北大和市","大和"],
    "涼邨山鉄道涼邨山線": ["涼邨","涼邨山"],
    "涼邨山鉄道猫屋敷本線": ["市川","西大石","涼鉄苅田","九十和","西九十和","涼鉄二見川","大和大原","涼鉄月新座","九十九空港2ビル","九十九空港1ビル","海風","烏原","和生","鳳街道","中川","朝日奈","アニメの街東栄","西東栄","盛原","木村","林村","小林","明智","叡智の森","東奥山","奥山","西奥山","迷いの森","紅葉振分","唐津","狼森","猫屋敷"],
    "阪神交通局九十九本線": ["九十九","九十九南","九十九市","九十九センタープール","九十九丹京","丹京市","丹京北","九十九大橋","丹京西"],
    "阪神交通局神明支線": ["丹京市","神明","神明市","新神明"],
    "阪神交通局九十九支線": ["九十九地下","東九十九","鉄道博物館","鏡石"],
    "涼邨山鉄道大泉本線": ["プリキュア博物館前","大泉高校前","大泉学園","小泉中等前","小泉学園","新花依","涼鉄栗山","鉄道博物館前","法矢","雲雀丘","吉水街道","初音","箕久原","飯納","我野","山平","粂川","東邨山","南東栄","アニメの町東栄","都営東栄住宅","原西","古原","秦台直通記念館","森亜","北森亜","安奈","松田","南北郷","北郷中央"],
    "夏海急行線": ["来海","中来海","中山","中浜","暑邨","狭海","南探原","探原","南三里","三里大原","二里大原","一里大原","烏浜零里大原","烏鳥羽","夏海"],
    "秦代交通線": ["夢川","伸舞雪","秦舞","秦代台団地","秦代","支線秦代","弧山","西川口","登山道入り口前","支線輪兎","輪兎","凛憐","重音","ボカロパーク前","李空","美玖","夢山","シンフォニー夢の森","神姫新坂","夢川車保セ横","光山","夢川車庫","夢川車セ","夢川研究所前","夢川ショッピングセンター前","河紗希","琥珀河","紅葉車庫センター入り口前","紅葉台車庫","紅葉台団地","尾英","総合福祉センター","松多","尾英車庫前","尾英総合車両センター横"]
}

# ===== 状態管理 =====
last_congestion = {}  # 混雑履歴
ongoing_closures = {}  # 運休中 {(line, station, trouble): end_time}

# ===== 時間チェック =====
def in_service_time():
    now = datetime.now().hour
    return 5 <= now or now < 1  # 5:00~1:00

def is_rush_hour():
    h = datetime.now().hour
    return 7 <= h <= 9 or 17 <= h <= 19

# ===== 運転支障選択 =====
def get_trouble():
    base = {
        "お客様トラブル":1,
        "線路内人立ち入り":1,
        "信号トラブル":1,
        "乗務員喧嘩":1,
        "混雑":1,
        "人身事故":1
    }
    if is_rush_hour(): base["混雑"] *= 2
    names = list(base.keys())
    weights = list(base.values())
    return random.choices(names, weights=weights)[0]

# ===== 補正 =====
def adjust_probability(trouble,line,station):
    mult = 1
    if trouble=="混雑":
        if line in ["夏海急行線","一ノ瀬新線","一ノ瀬本線","秦代交通線"]: mult*=0.5
        if station=="プリキュア博物館前" and is_rush_hour(): mult*=10
    if trouble=="お客様トラブル":
        if station in ["北郷中央","プリキュア博物館前","九十九空港1ビル","九十九"]: mult*=5
    if trouble=="人身事故":
        if line in ["秦代交通線","夏海急行線","涼邨山鉄道涼邨本線"]: mult*=10
    return mult

# ===== 起動 =====
@bot.event
async def on_ready():
    print("起動完了")
    if not loop.is_running():
        loop.start()

# ===== !test コマンド =====
@bot.command()
async def test(ctx):
    await ctx.send("現在遅延の情報を提供しております。")

# ===== メインループ =====
@tasks.loop(seconds=60)  # テスト用は1秒に変更可能
async def loop():
    if not in_service_time(): return
    now = datetime.now()
    time_str = now.strftime("%H:%M")

    # 復旧通知
    to_remove = []
    for key,end_time in ongoing_closures.items():
        if now >= end_time:
            line,station,trouble = key
            for cid in CHANNEL_IDS:
                ch = bot.get_channel(cid)
                if ch:
                    msg = await ch.send(f"<@&{ROLE_ID}>\n【運行情報 {time_str}現在】\n{line}は、{station}駅での{trouble}による運休が終了しました。")
                    try: await msg.publish()
                    except: pass
            to_remove.append(key)
    for key in to_remove: del ongoing_closures[key]

    # 新規支障発生
    if random.random() > 0.02: return
    line = random.choice(list(lines_data.keys()))
    station = random.choice(lines_data[line])
    trouble = get_trouble()
    mult = adjust_probability(trouble,line,station)
    if random.random() > mult: return

    # 混雑制限
    if trouble=="混雑":
        if station in last_congestion and now-last_congestion[station]<timedelta(hours=1): return
        last_congestion[station]=now
        delay=random.randint(5,10)
        text=f"{line}は、{station}駅の混雑の影響により遅れが発生しています（最大{delay}分）"
    else:
        # 運休支障
        if trouble in ["線路内人立ち入り","信号トラブル","乗務員喧嘩","人身事故","お客様トラブル"]:
            if trouble=="線路内人立ち入り": dur=random.randint(5,20); area="全線" if line in ["涼邨山鉄道涼邨山線","阪神交通局九十九支線","阪神交通局神明支線"] else "一部区間"
            elif trouble=="信号トラブル": dur=random.randint(5,60); area="全線" if line in ["涼邨山鉄道涼邨山線","阪神交通局九十九支線","阪神交通局神明支線"] else "一部区間"
            elif trouble=="乗務員喧嘩": dur=random.randint(5,20); area="一部列車"
            elif trouble=="人身事故": dur=random.randint(40,200); full=line in ["涼邨山鉄道涼邨山線","阪神交通局九十九支線","阪神交通局神明支線"] or random.random()<0.3; area="全線" if full else "一部区間"
            elif trouble=="お客様トラブル": dur=random.randint(5,15); area="一部列車"
            text=f"{line}は、{station}駅での{trouble}の影響により{area}で運休しています。再開後も最大{dur}分の遅れが見込まれます"
            ongoing_closures[(line,station,trouble)] = now + timedelta(minutes=dur)
        else:
            text=f"{line}は、{station}駅で{trouble}の影響により運休や遅延が発生しています"

    # 送信
    for cid in CHANNEL_IDS:
        ch = bot.get_channel(cid)
        if ch:
            msg = await ch.send(f"<@&{ROLE_ID}>\n【運行情報 {time_str}現在】\n{text}")
            try: await msg.publish()
            except: pass

# ===== トークン =====
import os

TOKEN = os.getenv("DISCORD_TOKEN")
