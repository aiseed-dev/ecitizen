// matplotlib SVG (text版) の実レンダリング検証。
// flutter_svgの非同期デコードはfake-asyncとハングするため、runAsync内で
// vector_graphicsのローダを直接叩いてPNGに書き出す (goldenは使わない)。
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_svg/flutter_svg.dart';

void main() {
  testWidgets('pyramid text-SVG renders to PNG with BIZ UD font',
      (tester) async {
    await tester.runAsync(() async {
      final fontData = File('assets/fonts/BIZUDGothic-Regular.ttf')
          .readAsBytesSync();
      final loader = FontLoader('BIZ UDGothic')
        ..addFont(Future.value(ByteData.view(fontData.buffer)));
      await loader.load();

      final svg = File('test/pyramid_fixed.svg').readAsStringSync();
      final info = await vg.loadPicture(SvgStringLoader(svg), null);
      final image = await info.picture.toImage(760, 640);
      final png = await image.toByteData(format: ui.ImageByteFormat.png);
      File('test/render_fixed.png')
          .writeAsBytesSync(png!.buffer.asUint8List());
      expect(png.lengthInBytes, greaterThan(5000));
    });
  });
}
