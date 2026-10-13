# filter-browser-ios 引き継ぎファイル（このファイル1つで完結）

このファイルは3部構成です。

1. Macでの始め方（この章だけ読めば着手できる）
2. CLAUDE.md の内容（新しいフォルダに `CLAUDE.md` として保存する）
3. 設計書 DESIGN.md の内容（新しいフォルダに `docs/DESIGN.md` として保存する）

元の設計書（図付き、Claude Docs）: https://claude.ai/code/artifact/762ca641-524d-4d43-8089-986004edf4a0

---

# 第1部: Macでの始め方

## 手順

1. 作業フォルダを作る。

```bash
mkdir ~/filter-browser-ios && cd ~/filter-browser-ios
mkdir docs
```

2. このファイルから第2部を `CLAUDE.md`、第3部を `docs/DESIGN.md` として保存する。
   手で切り出してもよいし、このファイルを `HANDOFF.md` としてフォルダに置き、Claude Code に次のように頼んでもよい。

> HANDOFF.md を読んで、第2部を CLAUDE.md、第3部を docs/DESIGN.md に切り出して保存して

3. Claude Code を入れていなければ入れる。

```bash
npm install -g @anthropic-ai/claude-code
```

4. フォルダで Claude Code を起動して、最初の指示を出す。

```bash
cd ~/filter-browser-ios
claude
```

> CLAUDE.md と docs/DESIGN.md を読んで、未決事項を私に確認してから第1段階を始めて

5. GitHub にリポジトリを作る場合は、GitHub の Web 画面で「New repository」（名前は仮に `filter-browser-ios`、Private）を作ってから次を実行する。

```bash
git init && git add . && git commit -m "Initial design"
git remote add origin https://github.com/k719578/filter-browser-ios.git
git push -u origin main
```

## 着手前に決めること

- リポジトリを公開（オープンソース）にするか。公開なら AdGuard の変換器（GPL-3.0）をそのまま使える。非公開なら変換器を差し替える。これが設計に一番効く。
- アプリ名。YouTube を連想させない汎用ブラウザの名前。

## 注意

- Xcode が必要になるのは第1段階のビルドから。Claude Code は Swift を書けるが、ビルドと実機確認は Xcode で行う。
- クラウド側の会話は Mac に引き継がれない。結論はすべて第2部と第3部に書いてある。

---

# 第2部: CLAUDE.md

# プロジェクト概要

iOS 向けの汎用ブラウザ（SwiftUI + WKWebView）。初期ホームは YouTube で、公開フィルタリストで広告を消し、Shorts を非表示にする。
YouTube 専用アプリとしては作らない（App Store 配布のため）。設計の全文は `docs/DESIGN.md`。着手前に必ず読むこと。

## 決定済みの方針（変更しない）

- Brave 型。汎用ブラウザ + 汎用フィルタ。アプリ名・説明文・コードに「YouTube 専用」「広告ブロック」を前面に出さない。
- 広告除去は AdGuard の公開資産を使う: SafariConverterLib（変換）、Scriptlets（json-prune 等）、ExtendedCss、AdGuard フィルタリスト。
- YouTube 専用のスキップ JS、クライアント偽装、InnerTube 直叩き、動画ダウンロードは入れない。
- Shorts 非表示は「要素非表示フィルタのプリセット」として実装し、設定でオンオフできる。
- 対応 OS は iOS 17 以上。永続化は SwiftData。

## 開発の進め方

- 3 段階で進める（DESIGN.md 11 章）。第 1 段階: 表示 + 通信遮断 + Shorts プリセット。第 2 段階: スクリプトレット注入。第 3 段階: 汎用ブラウザ化と審査対策。
- 第 2 段階の「非 Premium アカウントで動画内広告が出ない」が最初の関門。ここを越えるまで汎用ブラウザ機能には手を入れない。
- WKUserScript は必ず `injectionTime: .atDocumentStart`、`forMainFrameOnly: false`、`contentWorld: .page`。ひとつでも違うとスクリプトレットが効かない。
- FilterEngine パッケージは UIKit/SwiftUI 非依存にして `swift test` で回せるようにする。
- 実機確認が必要な項目は DESIGN.md のチェックリストに沿って、1 往復 1 項目で進める。

## 未決事項（最初に決める）

- リポジトリを公開（オープンソース）にするか。公開なら SafariConverterLib（GPL-3.0）をそのまま使える。非公開なら変換器を adblock-rust（MPL-2.0）に変えるか自作する。
- アプリ名（YouTube を連想させない汎用ブラウザの名前）。
- バックグラウンド再生、iPad 対応の程度、有料化の有無。

## 最初にやること

1. 未決事項の 1 つ目（公開/非公開）を決める。
2. `App/` に Xcode プロジェクト（SwiftUI, iOS 17）、`Packages/FilterEngine` と `Packages/FilterUpdater` に Swift Package を作る。
3. WKWebView で m.youtube.com を表示し、下タブ（ホーム・検索・登録チャンネル・ライブラリ）で URL を切り替える。
4. 同梱フィルタを SafariConverterLib で変換して WKContentRuleList に登録する。
5. Shorts プリセットの CSS を注入し、実機で DESIGN.md のチェックリストを通す。

---

# 第3部: docs/DESIGN.md

# YouTube最適化ブラウザ 設計書

作成日: 2026-10-08

元の設計書（Claude Docs、図付き）: https://claude.ai/code/artifact/762ca641-524d-4d43-8089-986004edf4a0

## 1. 目的と基本方針

App Storeで配布できる汎用ブラウザとして作り、初期設定でYouTubeがShortsなし・広告なしで快適に見られる状態にする。YouTube専用アプリとしては作らない。

**作るもの**

- iOS向けのWebKitブラウザ。URLバー、タブ、ブックマーク、履歴を持つ普通のブラウザとして成立させる。
- 初期ホームはYouTube。下タブはホーム・検索・登録チャンネル・ライブラリで、YouTubeアプリと同じ操作感にする。
- 広告除去は公開フィルタリスト（AdGuard、EasyList系）を取り込んで適用する。YouTube専用のスキップ処理は書かない。
- Shorts非表示は「要素非表示フィルタ」のプリセットとして提供する。

**Brave型を選ぶ理由**

- Braveは汎用ブラウザに汎用フィルタを積む構成でApp Storeに載っている。同じ構成なら審査とGoogle対応の両方に正面から説明できる。
- YouTube専用の広告除去アプリは審査ガイドライン5.2.2（他社サービスの利用規約遵守）で落ち、通っても後から削除された前例がある。
- フィルタの保守は公開リストの保守者が担う。このアプリは取りに行って適用するだけで、YouTube側の仕様変更に自前で追従しなくてよい。

**広告ゼロの位置づけ**

- 正規に完全ゼロにできるのはYouTube Premiumだけ。Premiumでログインすれば本アプリでも完全ゼロになる。
- 非Premiumでは、通信遮断・要素非表示・スクリプトレットの3段構えで「普段はゼロ、フィルタ更新待ちの期間だけ漏れる」を目標にする。完全ゼロは約束しない。

## 2. 要件

**機能要件**

| 分類 | 要件 | 優先 |
| --- | --- | --- |
| 閲覧 | WKWebViewで任意のURLを表示。戻る・進む・再読み込み・共有 | 必須 |
| YouTube導線 | 下タブ（ホーム・検索・登録チャンネル・ライブラリ）でYouTubeの各ページへ直行 | 必須 |
| ログイン維持 | GoogleアカウントのCookieを永続化し、登録・履歴・おすすめを使える | 必須 |
| 通信遮断 | 公開フィルタのネットワークルールをWKContentRuleListで適用 | 必須 |
| 要素非表示 | フィルタのCSSルールをサイトごとに注入 | 必須 |
| スクリプトレット | json-prune等をページ読み込み前に注入 | 必須 |
| Shorts非表示 | 要素非表示のプリセットとしてオンオフ可。/shorts/ URLは /watch に転送 | 必須 |
| フィルタ更新 | 起動時と定期に自動取得。失敗時は同梱版へフォールバック | 必須 |
| ピクチャインピクチャ | 動画をPiPで小窓再生 | 必須 |
| タブ | 複数タブの開閉と切替 | 必須（審査用） |
| ブックマーク・履歴 | 追加・削除・検索 | 必須（審査用） |
| カスタムフィルタ | ユーザーが任意のフィルタ行を追加できる | 推奨 |
| バックグラウンド再生 | 画面オフで音声継続 | 任意（要検証） |

**非機能要件**

- 対応 OS は iOS 17 以上。iPhone 優先、iPad は表示崩れがない程度。
- フィルタのコンパイルはバックグラウンドで行い、初回起動でも同梱版で即時にブロックが効く。
- ページ表示の体感速度は Safari と同等。スクリプトレット注入で読み込みが目に見えて遅くならない。
- フィルタ配信元が落ちていてもアプリは起動し、前回取得分で動く。
- ユーザーの閲覧データを外部に送らない。通信先はフィルタ配信元とユーザーが開くサイトだけ。

**やらないこと**

- YouTube Data API や内部API（InnerTube）を直接叩かない。動画のストリーム直接取得もしない。
- 動画のダウンロード機能は作らない（審査ガイドライン 5.2.3）。
- YouTube のプレイヤーやUIを自前で作り直さない。表示はすべて m.youtube.com のページそのもの。
- YouTube 専用の広告スキップコードやクライアント偽装は入れない。

## 3. 全体アーキテクチャ

アプリは UI、ブラウザ、フィルタエンジン、配信の4層で、公開フィルタを WebKit の2つの入口（WKContentRuleList と WKUserScript）に流し込む。YouTube の表示そのものは WKWebView に任せ、アプリはその周りを囲むだけ。

```
┌─ UI層 (SwiftUI) ────────────────────────────────────────────────┐
│  [下タブ]            [URLバー・タブ一覧]        [設定画面]           │
│  YouTube の各ページへ  汎用ブラウザ機能          リスト・プリセットのオンオフ │
└──────┬──────────────────────────────────────────────────────────┘
       │ URL 切替
┌──────▼──────────────────────────────────────────────────────────┐
│ ブラウザ層 (WebKit)                                               │
│  [WKWebView]                        [navigationDelegate]         │
│  m.youtube.com をそのまま表示          /shorts/ を /watch に転送      │
└──────▲──────────────────▲───────────────────────────────────────┘
       │ 遮断ルール          │ WKUserScript
┌──────┴──────────────────┴───────────────────────────────────────┐
│ フィルタエンジン層 (FilterEngine)                                   │
│  [Converter] ──▶ [RuleStore]                 [InjectionBuilder]  │
│  SafariConverterLib  WKContentRuleList で通信遮断  CSS とスクリプトレット注入 │
└──────▲──────────────────────────────────────────────────────────┘
       │ リスト原文
┌──────┴──────────────────────────────────────────────────────────┐
│ 配信層 (FilterUpdater)                                            │
│  [FilterUpdater] ◀── [配信元 / 同梱リスト]                          │
│  12時間ごとに取得、失敗時は前回分   AdGuard Base, Mobile, Japanese, EasyPrivacy │
└─────────────────────────────────────────────────────────────────┘
```

設定画面はリストとプリセットのオンオフを書き換え、Converter は通信ルールを RuleStore へ、要素非表示とスクリプトレットを InjectionBuilder へ渡す。ページを開くたびに、通信はルールリストで止まり、読み込み開始時に注入スクリプトが走る。

## 4. 画面設計

画面は「下タブでYouTubeの主要ページへ飛ぶ」を中心に、汎用ブラウザ機能は上部のURLバーとタブボタンに寄せる。WebViewはアプリ全体で1タブにつき1つで、下タブはそのWebViewのURLを切り替えるだけ。

**下タブと遷移先**

| タブ | 遷移先URL | 備考 |
| --- | --- | --- |
| ホーム | https://m.youtube.com/ | おすすめ。Shorts棚はフィルタで非表示 |
| 検索 | https://m.youtube.com/results?search\_query= | タップ時にページ内の検索欄へフォーカス |
| 登録チャンネル | https://m.youtube.com/feed/subscriptions | 要ログイン |
| ライブラリ | https://m.youtube.com/feed/library | 履歴・後で見る・再生リスト |
| メニュー | ネイティブ画面 | タブ一覧・ブックマーク・履歴・設定 |

現在のURLがタブの遷移先と一致するとき、そのタブを選択状態にする。動画再生中は下タブを残したまま、ページ側のミニプレイヤーに任せる。

**上部バー**

- 左: 戻る。長押しで履歴リスト。
- 中央: URLバー。タップで編集、入力中は履歴とブックマークから候補を出す。ブロック件数をバッジで表示。
- 右: タブ数ボタンとメニュー。
- スクロールで上部バーを縮小し、動画視聴中は画面を広く使う。

**動画再生**

- 再生は m.youtube.com のプレイヤーをそのまま使う。全画面、画質、字幕、再生速度はページ側の機能。
- WKWebView の allowsPictureInPictureMediaPlayback を有効にし、アプリを離れたら自動でPiPに入る。
- allowsInlineMediaPlayback を有効にし、タップで勝手に全画面にならないようにする。
- mediaTypesRequiringUserActionForPlayback は空にし、ページ側の自動再生を許す。

**設定画面**

- フィルタ: 有効なリストの一覧とオンオフ、最終更新日時、「今すぐ更新」。
- プリセット: 「Shortsを隠す」「コメントを隠す」などのトグル。実体はカスタムフィルタ行の束。
- カスタムフィルタ: ユーザーがフィルタ構文の行を直接追加できるテキスト欄。
- サイトごとの例外: このサイトではブロックを切る。
- プライバシー: Cookieとサイトデータの削除、履歴の削除。
- このアプリについて: バージョン、使用ライブラリとフィルタリストのライセンス表示。

## 5. フィルタエンジン設計

フィルタエンジンは公開フィルタリストを「通信遮断」「要素非表示」「スクリプトレット」の3種に仕分け、それぞれWebKitの対応する仕組みに流し込む。変換はAdGuardの公開ライブラリに任せ、自前のパーサは書かない。

**5.1 通信遮断（WKContentRuleList）**

- 入力: フィルタリストのネットワークルール（`||example.com^$third-party` 形式）。
- 変換: AdGuard SafariConverterLib で Safari コンテンツブロッカーJSONに変換する。変換できないルールは捨て、件数をログに残す。
- 適用: WKContentRuleListStore.compileContentRuleList でコンパイルし、リストごとに別識別子で登録する。コンパイル済みのものはOSがキャッシュするので、リストのハッシュが同じなら再コンパイルしない。
- 上限: 1リストあたり15万件を目安にし、超える場合は分割して複数登録する。
- 限界: この層だけでは動画内広告は消えない。広告動画も本編と同じ googlevideo.com から配信されるため。

**5.2 要素非表示（CSS注入）**

- 入力: `##` 形式のセレクタルール。ドメイン指定ありと汎用の2種。
- 適用: ページ読み込み開始時に、そのドメインに該当するセレクタを `{ display: none !important }` の `<style>` として WKUserScript で注入する。
- 拡張セレクタ（`:has()`, `:contains()` など）は AdGuard ExtendedCss を同じ注入で動かす。WebKitは `:has()` をネイティブ対応しているので、可能なものはCSSで済ませる。
- SPA対応: YouTubeはページ遷移してもリロードしないので、注入したCSSは最初の1回で全ページに効く。追加のMutationObserverは不要。

**5.3 スクリプトレット注入（ここが成否の山場）**

- 入力: `example.com#%#//scriptlet('json-prune', '...')` 形式の行。YouTube向けは json-prune でプレイヤー応答JSONから広告配置情報（adPlacements, playerAds, adSlots）を削るものが中心。
- 実体: AdGuard Scriptlets ライブラリのJSを同梱し、ドメインごとに該当するスクリプトレットと引数を組み立てて注入する。
- 注入条件は3つすべて満たすこと。ひとつでも外れると全く効かない。
  1. injectionTime は `.atDocumentStart`。YouTubeのスクリプトが JSON.parse や fetch を呼ぶ前に差し替えを済ませる。
  2. contentWorld は `.page`。隔離ワールドに注入するとページの JSON.parse とは別物になり、差し替えが届かない。
  3. forMainFrameOnly は `false`。埋め込みプレイヤーや広告のiframeにも効かせる。
- ドメイン判定は注入したJSの先頭で `location.hostname` を見て行う。WKUserScript はドメインごとに出し分けられないため、全ドメイン分を一つのスクリプトにまとめて入れ、実行時に振り分ける。
- 広告ブロック検知の警告画面も、同じリストのスクリプトレット（set-constant 等）で抑える。専用コードは書かない。

**5.4 Shorts非表示プリセット**

プリセットはカスタムフィルタ行の束で、ユーザーが設定でオンオフする。セレクタは実機で確認して確定する。初期案は次の通り。

| 対象 | 初期案（要実機確認） |
| --- | --- |
| ホームのShorts棚 | `m.youtube.com##ytm-reel-shelf-renderer` |
| 下ナビのShortsタブ | `m.youtube.com##ytm-pivot-bar-item-renderer:has(a[href^="/shorts"])` |
| 検索結果のShorts | `m.youtube.com##ytm-reel-item-renderer` |
| チャンネルのShortsタブ | `m.youtube.com##ytm-c4-tabbed-header-renderer [tab-title="Shorts"]` |
| /shorts/ への遷移 | ネイティブ側の decidePolicyFor で `/shorts/{id}` を `/watch?v={id}` に書き換え |

**5.5 フィルタリストの取得と更新**

| リスト | 役割 | 初期状態 |
| --- | --- | --- |
| AdGuard Base | 汎用広告。YouTube向けスクリプトレットを含む | 有効 |
| AdGuard Mobile Ads | モバイルサイトの広告 | 有効 |
| EasyPrivacy | 計測・トラッキング | 有効 |
| AdGuard Annoyances | Cookie同意バナー等 | 無効 |
| AdGuard Japanese | 日本のサイト向け | 有効 |
| プリセット（アプリ同梱） | Shorts非表示等 | 有効 |

更新の流れはこうする。

1. アプリにはビルド時点のリストを同梱し、初回起動でも即時に効く。
2. 起動時と前回から12時間以上経過したときに、バックグラウンドで配信元から取得する。
3. 取得成功と変換成功の両方を満たしたときだけ、新しいリストに入れ替える。失敗したら前回分を使い続ける。
4. 入れ替えは次に開くタブから効く。開いているタブは再読み込み時に新リストになる。
5. 配信元はリストごとに主・副の2つを持ち、主が落ちていたら副から取る。

## 6. 技術スタックと外部依存

アプリ本体は Swift と SwiftUI で書き、フィルタ変換とスクリプトレットは AdGuard の公開ライブラリを使う。外部依存はこの3つに絞る。

| 項目 | 採用 | 理由 |
| --- | --- | --- |
| 対応 OS | iOS 17 以上 | WKContentWorld と `:has()` が安定して使える |
| 言語 | Swift 5.10 以上 | - |
| UI | SwiftUI。WebView は UIViewRepresentable で包む | タブ・設定画面の工数が小さい |
| ブラウザエンジン | WKWebView | iOS ではこれ以外の選択肢がない |
| 通信遮断 | WKContentRuleList | OS 標準。プロセス外で動き速い |
| 注入 | WKUserScript（contentWorld: .page） | スクリプトレットに必須 |
| フィルタ変換 | AdguardTeam/SafariConverterLib（Swift Package） | AdGuard 構文を Safari JSON と高度ルールに分けて出力する |
| スクリプトレット | AdguardTeam/Scriptlets（ビルド済み JS を同梱） | json-prune 等の実装を自作しない |
| 拡張 CSS | AdguardTeam/ExtendedCss（ビルド済み JS を同梱） | `:contains()` 等の非標準セレクタ用 |
| 永続化 | SwiftData | ブックマーク・履歴・タブ用 |
| テスト | XCTest | 変換とドメイン振り分けの単体テスト |

**AdGuard を選ぶ理由**

- 変換器、スクリプトレット、フィルタリストの3点が同じ開発元で、構文が揃っている。uBlock Origin のリストを使うと構文差の吸収が必要になる。
- 変換器が Swift 製で、Rust や C のビルド環境を足さなくてよい。
- Brave の adblock-rust は代替候補。Rust ツールチェーンと FFI が必要になるので、AdGuard で足りなくなったときだけ検討する。

**ライセンス（着手時に原文で再確認）**

| 対象 | ライセンス | 影響 |
| --- | --- | --- |
| SafariConverterLib | GPL-3.0 と把握 | アプリ全体のソース公開義務が生じる可能性。公開前提で進めるか、別プロセス化を検討 |
| Scriptlets | MIT と把握 | 著作権表示のみ |
| ExtendedCss | MIT と把握 | 著作権表示のみ |
| AdGuard フィルタリスト | GPL-3.0 と把握 | データとして取得・適用する分には出典表示で足る。Brave も同様に利用 |
| EasyList / EasyPrivacy | GPL-3.0 と CC BY-SA 3.0 の二重 | 同上 |

リポジトリを公開（オープンソース）で進めれば GPL の問題は消える。非公開にしたい場合は変換器だけ自作するか、MPL-2.0 の adblock-rust に切り替える。これは未決事項に挙げる。

## 7. データ設計と永続化

永続化は「ユーザーデータは SwiftData、フィルタはファイル、Cookie は WebKit に任せる」の3系統に分ける。

| データ | 保存先 | 主な項目 |
| --- | --- | --- |
| タブ | SwiftData | id、現在URL、タイトル、最終表示日時、並び順 |
| ブックマーク | SwiftData | URL、タイトル、作成日時、フォルダ |
| 履歴 | SwiftData | URL、タイトル、訪問日時。保持期間は90日 |
| 設定 | UserDefaults | プリセットのオンオフ、リストのオンオフ、更新間隔、サイトごとの例外 |
| カスタムフィルタ | Application Support 内のテキストファイル | ユーザーが書いた行 |
| フィルタリスト原文 | Application Support/filters/{listId}.txt | 取得日時と ETag を別ファイルに持つ |
| 変換済み JSON | Application Support/compiled/{listId}.json | ハッシュを識別子にして WKContentRuleListStore に登録 |
| 変換済み高度ルール | Application Support/compiled/{listId}.advanced.json | 要素非表示とスクリプトレットをドメインで引ける形 |
| Cookie・サイトデータ | WKWebsiteDataStore.default() | Google ログイン。プライベートタブは nonPersistent() |

変換済みファイルは「原文のハッシュ + 変換器バージョン」をキーにし、どちらかが変わったときだけ作り直す。アプリ更新で変換器が上がったら全リストを再変換する。

## 8. モジュール構成とリポジトリ構造

フィルタエンジンを UI から切り離した Swift Package にし、変換と振り分けを Xcode なしでもテストできるようにする。新規リポジトリで始める。

```
Repo/
├─ App/                      Xcode プロジェクト。SwiftUI 画面と WebView ラッパー
│  ├─ Browser/               BrowserView, TabBar, URLBar, WebViewContainer
│  ├─ Settings/              設定画面
│  ├─ Store/                 SwiftData モデル（Tab, Bookmark, HistoryEntry）
│  └─ Resources/             同梱フィルタ、scriptlets.js、extended-css.js
├─ Packages/
│  ├─ FilterEngine/          変換・振り分け・注入スクリプト生成。UIKit 非依存
│  │  ├─ Sources/FilterEngine/
│  │  │  ├─ FilterList.swift        リスト定義（id, 名前, URL主/副, 既定オンオフ）
│  │  │  ├─ Converter.swift         SafariConverterLib 呼び出しと結果の振り分け
│  │  │  ├─ RuleStore.swift         WKContentRuleListStore の登録とキャッシュ
│  │  │  ├─ InjectionBuilder.swift  CSS とスクリプトレットを 1 本の JS に組み立て
│  │  │  └─ Presets.swift           Shorts 非表示等のプリセット定義
│  │  └─ Tests/FilterEngineTests/
│  └─ FilterUpdater/         取得・検証・差し替え。URLSession と BackgroundTasks
├─ Scripts/
│  └─ bundle-filters.sh      ビルド時に同梱リストを最新化
├─ docs/
│  └─ DESIGN.md              この設計書の写し
└─ README.md
```

**モジュール間の依存**

- App は FilterEngine と FilterUpdater に依存する。逆はない。
- FilterEngine は WebKit と SafariConverterLib に依存する。UIKit と SwiftUI には依存しない。
- FilterUpdater は FilterEngine に依存し、取得後の変換を FilterEngine に委ねる。

**WebView の組み立て順（WebViewContainer）**

1. WKWebViewConfiguration を作る。メディア設定と WKWebsiteDataStore を指定。
2. RuleStore から有効な WKContentRuleList を全部 userContentController に追加。
3. InjectionBuilder が生成した JS を WKUserScript（atDocumentStart, 全フレーム, .page）として追加。
4. WKWebView を生成し、navigationDelegate で /shorts/ 転送と外部スキームの扱いを決める。
5. タブの URL を読み込む。

## 9. App Store 審査対策

審査では「汎用ブラウザであること」と「ブロックがユーザーが選ぶ汎用フィルタであること」の2点が見られる。アプリの中身とストアの説明文の両方をそこに合わせる。

**命名と説明文**

- アプリ名、サブタイトル、キーワード、スクリーンショットに「YouTube」を入れない。YouTube のロゴや赤い再生ボタンを模したアイコンも使わない。
- 「広告ブロック」を売り文句にしない。「コンテンツブロッカー対応」「フィルタリスト対応」と書く。Brave と Safari の説明文の言い回しに寄せる。
- スクリーンショットは複数のサイトを開いた画面を使う。全部 YouTube にしない。
- カテゴリは「ユーティリティ」。年齢制限は「無制限のWebアクセス」を申告し、17+ になる。

**ガイドラインごとの回答**

| 条項 | 指摘されうる点 | こちらの根拠 |
| --- | --- | --- |
| 4.2 最低限の機能 | Webサイトを包んだだけ | URLバー、タブ、ブックマーク、履歴、フィルタ管理を持つ汎用ブラウザ |
| 5.2.2 他社サービス | YouTube の利用規約違反 | 特定サービスを対象にしていない。ブロックはユーザーが選ぶ公開フィルタで、Safari のコンテンツブロッカーと同じ仕組み |
| 5.2.3 メディアのダウンロード | 動画保存 | 機能を持たない |
| 2.5.6 WebKit 使用 | 独自エンジン | WKWebView のみ |
| 5.1.1 データ収集 | 閲覧データの送信 | 外部送信なし。プライバシーラベルは「データを収集しない」 |

**審査ノートに書くこと**

- コンテンツブロッカーは WKContentRuleList と WKUserScript で実装し、フィルタはユーザーが設定で選択する。
- 初期ホームは変更可能で、任意のURLを開ける。
- 設定画面への行き方と、フィルタを全部オフにする手順を明記する。

**審査を通った後の注意**

- Google からの申し立てで削除されるリスクは残る。専用コードを入れないこと、YouTube を名指ししないことが唯一の防御。
- アップデートでも同じ方針を崩さない。レビュー返信やストアの「新機能」欄で YouTube に触れない。

## 10. リスクと対策

最大のリスクは「スクリプトレット注入が実機で効かない」と「YouTube が広告を動画データに混ぜ込む」の2つ。前者は第2段階で最初に検証し、後者は設計では防げないと割り切る。

| リスク | 起きること | 対策 |
| --- | --- | --- |
| スクリプトレットが効かない | 動画内広告が残る | 第2段階の最初に json-prune 単体で実機検証。注入時点・ワールド・フレームの3条件をログで確認できるデバッグ画面を用意 |
| 広告ブロック検知 | 「広告ブロッカーは規約違反」の警告で再生停止 | 公開フィルタの更新待ち。更新間隔を設定で短くできるようにし、「今すぐ更新」を置く |
| サーバーサイド広告挿入 | 広告が動画データに混ざり、どの方式でも消せない | 設計では防げない。Premium への誘導文を設定画面に用意し、Shorts 非表示とブラウザとしての価値で成立させる |
| フィルタ配信元の停止 | 更新が止まり徐々に効かなくなる | リストごとに主・副の配信元。AdGuard が止まったら uBlock Origin の uAssets に切替（構文差の吸収が必要） |
| 変換でルールが落ちる | Safari 形式に変換できないルールが無視される | 落ちた件数をログと設定画面に出す。YouTube 向けの主要ルールが落ちていないかを単体テストで監視 |
| WebKit の制約 | コンテンツルールの件数上限、正規表現の制限 | リストを分割登録。変換器がこの制約を把握している |
| 審査リジェクト | 4.2 または 5.2.2 で落ちる | 第9章の対策。落ちたら指摘条項ごとに機能を足して再提出。広告除去を外すのは最後の手 |
| GPL の影響 | 変換器が GPL で、アプリのソース公開義務が生じる | リポジトリを公開するか、変換器を MPL の adblock-rust に変える。着手前に決める |
| パフォーマンス | 全ドメイン分の注入 JS が大きく、ページ表示が遅れる | 注入 JS はドメイン別の辞書を 1 つ持つだけにし、実行は該当ドメイン分のみ。サイズは 1MB を上限にする |

## 11. 開発フェーズと検証計画

3段階で進め、第2段階の「動画内広告が消えるか」を最初の関門にする。そこを越えるまで汎用ブラウザ機能には手を入れない。

| 段階 | 範囲 | 完了条件 | 目安 |
| --- | --- | --- | --- |
| 1 表示と通信遮断 | WebView、下タブ、ログイン維持、PiP、同梱リストの変換と適用、Shorts プリセット、/shorts/ 転送 | YouTube がアプリらしく操作でき、Shorts が全画面で消え、バナー広告が消える | 1週間 |
| 2 スクリプトレット | 注入基盤、AdGuard Scriptlets 組み込み、ドメイン振り分け、デバッグ画面、フィルタ自動更新 | 非 Premium アカウントで動画内広告が出ない。警告画面が出ない | 1〜2週間 |
| 3 汎用ブラウザ化 | URLバー、タブ、ブックマーク、履歴、設定画面、カスタムフィルタ、ライセンス表示、ストア素材 | 第9章の対策が全部入っている。TestFlight で配布できる | 1〜2週間 |

**進め方**

- コードは Claude が書き、ビルドと実機確認は Mac の Xcode で行う。Claude の作業環境には Xcode がない。
- 1往復の単位は「1つの確認項目」。スクリーンショットかデバッグ画面のログを貼ってもらえば次に進める。
- FilterEngine の変換と振り分けは Linux 上の swift test でも回せるように作り、実機なしで直せる範囲を広ける。

**実機チェックリスト（段階ごとに全部通す）**

- [ ] Google ログインがアプリ再起動後も維持される
- [ ] ホームに Shorts 棚が出ない
- [ ] 下ナビの Shorts タブが出ない
- [ ] 検索結果に Shorts が混ざらない
- [ ] チャンネルページに Shorts タブが出ない
- [ ] /shorts/ のリンクを開くと通常の視聴画面になる
- [ ] バナー・オーバーレイ広告が出ない
- [ ] 動画開始前の広告が出ない（非 Premium）
- [ ] 動画途中の広告が出ない（非 Premium、20分以上の動画で確認）
- [ ] 「広告ブロッカーが検出されました」の警告が出ない
- [ ] アプリを離れると PiP に入る
- [ ] 機内モードで起動してもフィルタが効いている
- [ ] フィルタを全部オフにすると広告と Shorts が戻る
- [ ] YouTube 以外のサイト（ニュースサイト等）でも広告が消え、表示崩れがない
- [ ] ページ表示が Safari と比べて目に見えて遅くない

## 12. 未決事項

着手前に決めるのは次の5点。上の2つは設計に影響する。

- [ ] リポジトリを公開（オープンソース）にするか。公開なら AdGuard の変換器をそのまま使える。非公開なら変換器を adblock-rust に変えるか自作する。
- [ ] アプリ名。YouTube を連想させない汎用ブラウザの名前。
- [ ] バックグラウンド再生を入れるか。実機で動くかの検証が先。
- [ ] iPad 対応の程度。表示さえすればよいか、サイドバーレイアウトまで作るか。
- [ ] 有料化するか。するなら課金で解除する機能をどれにするか。広告除去を課金対象にすると 5.2.2 のリスクが上がる。
