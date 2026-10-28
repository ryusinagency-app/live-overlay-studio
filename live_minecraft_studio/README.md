# Live Minecraft Studio

TikTok LIVEのギフトをMinecraft Java版サーバー内の埋め立てゲームへ反映する、Live Overlay Studioとは独立したアプリです。

## 初期版の機能

- JavaサーバーへRCON接続
- 基準座標とサイズから埋め立て用の枠を生成
- ブロック配置を小分けにした専用キュー
- 埋め立て、TNT、修復、全埋めの効果
- TNTが底へ到達したときの耐久ゲージとWIN減算
- 累計コインによる倍率タイム
- 効果一覧と進捗を表示する軽量オーバーレイ
- Live Overlay Studioへ返すWINイベントの保留・再送・重複防止
- 接続先がPaper系、Spigot系、Fabric系、Forge系、バニラ系かを自動判定
- 全埋め後の防衛カウント、破壊時のリセット、ギフトによる残り時間変更
- 次の破壊を無効化するシールド

## 起動

```powershell
py server.py
```

ブラウザーで `http://127.0.0.1:8775/` を開きます。

効果一覧オーバーレイは `http://127.0.0.1:8775/effects_overlay.html`、進捗・耐久オーバーレイは `http://127.0.0.1:8775/overlay.html` です。

Minecraftサーバーの `server.properties` ではRCONを有効にしてください。

```properties
enable-rcon=true
rcon.port=25575
rcon.password=十分に長いパスワード
```

RCONポートはインターネットへ公開せず、Minecraftサーバーと同じPCまたは信頼できるLAN内だけで利用してください。

