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
