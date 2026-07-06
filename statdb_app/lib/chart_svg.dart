/// ビルド時生成の matplotlib SVG チャートを表示する部品 (DESIGN.md §17)。
///
/// SVG は svg.fonttype='none' (テキスト保持) で生成し、フォントは
/// pubspec の BIZ UDGothic / BIZ UDPGothic (アプリ同梱) で解決する。
/// vector_graphics コンパイラでの互換性検証済み (text版は path版の1/7サイズ)。
library;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

class ChartSvg extends StatelessWidget {
  const ChartSvg.string(this.svg, {super.key}) : url = null;
  const ChartSvg.network(this.url, {super.key}) : svg = null;

  final String? svg;
  final String? url;

  @override
  Widget build(BuildContext context) {
    final picture = svg != null
        ? SvgPicture.string(svg!, fit: BoxFit.contain)
        : SvgPicture.network(url!, fit: BoxFit.contain,
            placeholderBuilder: (_) =>
                const Center(child: CircularProgressIndicator()));
    return AspectRatio(aspectRatio: 9.2 / 7.0, child: picture);
  }
}
