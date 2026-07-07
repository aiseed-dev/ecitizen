/// ビルド時生成の matplotlib SVG チャートを表示する部品 (DESIGN.md §17)。
///
/// SVG は svg.fonttype='none' (テキスト保持) で生成する。フォントは
/// 同梱せず名前指定のみ — BIZ UDGothic がインストール済みなら使われ、
/// 無ければ OS 既定にフォールバックする (Windows は標準搭載)。
/// vector_graphics コンパイラでの互換性検証済み (text版は path版の1/7サイズ)。
library;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_svg_cjk_friendly/flutter_svg_cjk_friendly.dart';

class ChartSvg extends StatelessWidget {
  const ChartSvg.string(this.svg, {super.key}) : url = null;
  const ChartSvg.network(this.url, {super.key}) : svg = null;

  final String? svg;
  final String? url;

  @override
  Widget build(BuildContext context) {
    final picture = svg != null
        ? SvgPicture.string(cjkFriendlySvg(svg!, preferred: const ['BIZ UDGothic', 'BIZ UDPGothic']), fit: BoxFit.contain)
        : SvgPicture.network(url!, fit: BoxFit.contain,
            placeholderBuilder: (_) =>
                const Center(child: CircularProgressIndicator()));
    return AspectRatio(aspectRatio: 9.2 / 7.0, child: picture);
  }
}
