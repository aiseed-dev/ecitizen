/// Statdb カタログのデータ層 (DATA_CONTRACT.md §2.9)。
///
/// 配信サイトの静的スナップショット JSON を fetch する。e-Stat API は
/// 呼ばない (K5)。ネイティブではアプリのサポートディレクトリにキャッシュし、
/// オフラインでもカタログ閲覧できるようにする (Web は HTTP キャッシュ任せ)。
library;

import 'dart:convert';
import 'dart:io' show File, Directory;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// --dart-define=STATDB_DATA_BASE=... で上書き可能 (開発時はローカルサーバー)。
/// Web は同一オリジンの /Statdb/data を自動解決 (ローカル確認・本番とも同じ)。
/// ネイティブは配信サイト固定。
const _envBase = String.fromEnvironment('STATDB_DATA_BASE');

String statdbDefaultBase() {
  if (_envBase.isNotEmpty) return _envBase;
  if (kIsWeb) return Uri.base.resolve('/Statdb/data').toString();
  return 'https://ecitizen.jp/Statdb/data';
}

const estatDbview = 'https://www.e-stat.go.jp/dbview?sid=';

const kindPrefix = {1: '', 2: 'T'};
const kindLabel = {1: '統計', 2: '小地域・地域メッシュ'};

class StatdbData {
  StatdbData({String? base}) : base = base ?? statdbDefaultBase();

  final String base;
  final Map<String, dynamic> _mem = {};

  Future<dynamic> _load(String rel) async {
    if (_mem.containsKey(rel)) return _mem[rel];

    String? body;
    File? cacheFile;
    if (!kIsWeb) {
      final dir = await getApplicationSupportDirectory();
      cacheFile = File('${dir.path}/statdb/$rel');
    }
    try {
      final resp = await http
          .get(Uri.parse('$base/$rel'))
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) {
        throw Exception('HTTP ${resp.statusCode}');
      }
      body = utf8.decode(resp.bodyBytes);
      if (cacheFile != null) {
        await Directory(cacheFile.parent.path).create(recursive: true);
        await cacheFile.writeAsString(body);
      }
    } catch (e) {
      // オフライン等: ディスクキャッシュがあればそれを使う
      if (cacheFile != null && await cacheFile.exists()) {
        body = await cacheFile.readAsString();
      } else {
        rethrow;
      }
    }
    final obj = json.decode(body);
    _mem[rel] = obj;
    return obj;
  }

  Future<Map<String, dynamic>> catalog() async =>
      (await _load('catalog.json')) as Map<String, dynamic>;

  Future<List<dynamic>> tableList(int kind, String code) async =>
      (await _load('list/${kindPrefix[kind]}$code.json')) as List<dynamic>;

  Future<List<dynamic>> latest() async =>
      (await _load('latest.json')) as List<dynamic>;

  Future<List<dynamic>> latestTables(String id) async =>
      (await _load('latest_tables/$id.json')) as List<dynamic>;

  Future<String> statName(int kind, String code) async {
    final cat = await catalog();
    for (final e in cat['stats'] as List<dynamic>) {
      if (e['kind'] == kind && e['id'] == code) return e['name'] as String;
    }
    return code;
  }
}

/// statics の空白区切り階層ツリー (旧 StatsClass.GetStatsClass の移植。
/// Flet 版 statdb_data.build_tree と同一ロジック)。
class TreeNode {
  final Map<String, TreeNode> children = {};
  int count = 0; // このノード名で statics が終端する表の数
}

TreeNode buildTree(List<dynamic> rows) {
  final root = TreeNode();
  final sorted = List<dynamic>.from(rows)
    ..sort((a, b) => (a['id'] as String).compareTo(b['id'] as String));
  for (final row in sorted) {
    final parts = (row['statics'] as String)
        .split(' ')
        .where((p) => p.isNotEmpty)
        .toList();
    var node = root;
    for (var i = 0; i < parts.length; i++) {
      node = node.children.putIfAbsent(parts[i], TreeNode.new);
      if (i == parts.length - 1) node.count++;
    }
  }
  return root;
}

/// statics 完全一致の統計表を表番号順に返す (旧 StatsTitleList 相当)。
List<dynamic> filterTables(List<dynamic> rows, String statics) {
  final hits = rows.where((r) => r['statics'] == statics).toList()
    ..sort((a, b) => (a['sequence'] as String).compareTo(b['sequence'] as String));
  return hits;
}
