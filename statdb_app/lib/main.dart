/// 統計データAPI エクスプローラ - Flutter 版 (DESIGN.md §17、K13)。
///
/// 画面フローは Flet 版 (statdb_flet/main.py) と共通。旧サイトの URL 構造を
/// go_router のルートとして踏襲する (ブックマーク互換は _redirects で吸収)。
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import 'data.dart';

final data = StatdbData();

void main() {
  runApp(const StatdbApp());
}

final _router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, s) => const HomeScreen()),
    GoRoute(
      path: '/stats/:kind/:code',
      builder: (_, s) => TreeScreen(
        kind: int.parse(s.pathParameters['kind']!),
        code: s.pathParameters['code']!,
        path: '',
      ),
    ),
    GoRoute(
      path: '/stats/:kind/:code/:path',
      builder: (_, s) => TreeScreen(
        kind: int.parse(s.pathParameters['kind']!),
        code: s.pathParameters['code']!,
        path: Uri.decodeComponent(s.pathParameters['path']!),
      ),
    ),
    GoRoute(
      path: '/tables/:kind/:code/:statics',
      builder: (_, s) => TablesScreen(
        kind: int.parse(s.pathParameters['kind']!),
        code: s.pathParameters['code']!,
        statics: Uri.decodeComponent(s.pathParameters['statics']!),
      ),
    ),
    GoRoute(path: '/latest', builder: (_, s) => const LatestScreen()),
    GoRoute(
      path: '/latest/:id',
      builder: (_, s) => LatestTablesScreen(id: s.pathParameters['id']!),
    ),
  ],
);

class StatdbApp extends StatelessWidget {
  const StatdbApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: '統計データAPI エクスプローラ - 統計メモ帳',
      theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
      routerConfig: _router,
    );
  }
}

/// FutureBuilder の共通ラッパー (ロード中スピナー+エラー表示)。
class Loader<T> extends StatelessWidget {
  const Loader({super.key, required this.future, required this.builder});

  final Future<T> future;
  final Widget Function(BuildContext, T) builder;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: future,
      builder: (context, snap) {
        if (snap.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text('データを読み込めませんでした: ${snap.error}'),
            ),
          );
        }
        if (!snap.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        return builder(context, snap.data as T);
      },
    );
  }
}

ListTile tableTile(dynamic r, {bool showStatics = false}) {
  final no = (r['no'] == '-' || r['no'] == '') ? '' : '表${r['no']} ';
  final String info;
  if (showStatics) {
    info = r['statics'] as String;
  } else {
    final sdate = r['sdate'] == '0' ? '-' : r['sdate'];
    final num = r['num'];
    info = '調査年月: $sdate'
        '${num != null ? ' / $num件' : ''} / 公開: ${r['open']}';
  }
  final sid = (r['id'] ?? r['stats_data_id']) as String;
  return ListTile(
    dense: true,
    title: Text('$no${r['title']}', style: const TextStyle(fontSize: 14)),
    subtitle: Text(info, style: const TextStyle(fontSize: 12)),
    trailing: const Icon(Icons.open_in_new, size: 18),
    onTap: () => launchUrl(Uri.parse('$estatDbview$sid'),
        mode: LaunchMode.externalApplication),
  );
}

// ---- ホーム: 統計名一覧 + 検索 ----

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _keyword = '';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('統計データAPI エクスプローラ')),
      body: Loader<Map<String, dynamic>>(
        future: data.catalog(),
        builder: (context, catalog) {
          final tiles = <Widget>[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Text(
                '政府統計の総合窓口 (e-Stat) の統計データAPIで提供されている'
                '統計データの一覧です。統計表は e-Stat の統計表表示画面で開きます。'
                ' (カタログ取得日: ${catalog['fetched_at'] ?? '-'})',
                style: const TextStyle(fontSize: 13),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: TextField(
                decoration: const InputDecoration(
                  hintText: '統計名で検索 (例: 国勢調査)',
                  prefixIcon: Icon(Icons.search),
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                onChanged: (v) => setState(() => _keyword = v.trim()),
              ),
            ),
          ];
          for (final kind in [1, 2]) {
            final stats = (catalog['stats'] as List<dynamic>)
                .where((e) =>
                    e['kind'] == kind &&
                    (_keyword.isEmpty ||
                        (e['name'] as String).contains(_keyword)))
                .toList();
            if (stats.isEmpty) continue;
            tiles.add(Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(kindLabel[kind]!,
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 16)),
            ));
            tiles.addAll(stats.map((e) => ListTile(
                  dense: true,
                  title: Text(e['name'] as String),
                  subtitle: Text('${e['id']} (${e['gov_org']})',
                      style: const TextStyle(fontSize: 12)),
                  onTap: () => context.push('/stats/${e['kind']}/${e['id']}'),
                )));
          }
          return ListView(children: tiles);
        },
      ),
    );
  }
}

// ---- 階層ドリルダウン (最上位は統計内全表の横断検索つき) ----

class TreeScreen extends StatefulWidget {
  const TreeScreen(
      {super.key, required this.kind, required this.code, required this.path});

  final int kind;
  final String code;
  final String path;

  @override
  State<TreeScreen> createState() => _TreeScreenState();
}

class _TreeScreenState extends State<TreeScreen> {
  String _keyword = '';

  @override
  Widget build(BuildContext context) {
    final parts = widget.path.isEmpty ? <String>[] : widget.path.split(' ');
    return Loader<List<dynamic>>(
      future: data.tableList(widget.kind, widget.code),
      builder: (context, rows) {
        var node = buildTree(rows);
        for (final name in parts) {
          node = node.children[name] ?? TreeNode();
        }

        final List<Widget> tiles;
        if (parts.isEmpty && _keyword.length >= 2) {
          // 統計内の全表横断検索 (表題・統計名の部分一致)
          final hits = rows
              .where((r) =>
                  (r['title'] as String).contains(_keyword) ||
                  (r['statics'] as String).contains(_keyword))
              .toList()
            ..sort((a, b) {
              final c =
                  (a['statics'] as String).compareTo(b['statics'] as String);
              return c != 0
                  ? c
                  : (a['sequence'] as String)
                      .compareTo(b['sequence'] as String);
            });
          tiles = [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Text(
                '${hits.length}表がヒット'
                '${hits.length > 300 ? " (先頭300件を表示)" : ""}',
                style: const TextStyle(fontSize: 12),
              ),
            ),
            ...hits.take(300).map((r) => tableTile(r, showStatics: true)),
          ];
        } else {
          tiles = [
            if (node.count > 0)
              ListTile(
                dense: true,
                leading: const Icon(Icons.table_chart),
                title: Text('この階層の統計表 (${node.count}件)'),
                onTap: () => context.push(
                    '/tables/${widget.kind}/${widget.code}/'
                    '${Uri.encodeComponent(widget.path.isEmpty ? widget.code : widget.path)}'),
              ),
            ...node.children.entries.map((e) {
              final label =
                  e.key + (e.value.count > 0 ? ' (${e.value.count}件)' : '');
              final childPath =
                  widget.path.isEmpty ? e.key : '${widget.path} ${e.key}';
              final hasChildren = e.value.children.isNotEmpty;
              return ListTile(
                dense: true,
                leading: Icon(hasChildren
                    ? Icons.folder_outlined
                    : Icons.table_chart_outlined),
                title: Text(label),
                trailing:
                    hasChildren ? const Icon(Icons.chevron_right) : null,
                onTap: () => context.push(hasChildren
                    ? '/stats/${widget.kind}/${widget.code}/${Uri.encodeComponent(childPath)}'
                    : '/tables/${widget.kind}/${widget.code}/${Uri.encodeComponent(childPath)}'),
              );
            }),
          ];
        }

        final title = parts.isNotEmpty
            ? Future.value(parts.last)
            : data.statName(widget.kind, widget.code);
        return Scaffold(
          appBar: AppBar(
            title: Loader<String>(future: title, builder: (_, t) => Text(t)),
          ),
          body: Column(children: [
            if (parts.isEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: TextField(
                  decoration: InputDecoration(
                    hintText: 'この統計の全${rows.length}表から検索 (表題・統計名)',
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: (v) => setState(() => _keyword = v.trim()),
                ),
              ),
            Expanded(child: ListView(children: tiles)),
          ]),
        );
      },
    );
  }
}

// ---- 統計表一覧 ----

class TablesScreen extends StatelessWidget {
  const TablesScreen(
      {super.key,
      required this.kind,
      required this.code,
      required this.statics});

  final int kind;
  final String code;
  final String statics;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(statics.split(' ').last)),
      body: Loader<List<dynamic>>(
        future: data.tableList(kind, code),
        builder: (context, rows) {
          final hits = filterTables(rows, statics);
          return ListView(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Text(
                '統計表をタップすると e-Stat の統計表表示画面を開きます'
                ' (${hits.length}件)',
                style: const TextStyle(fontSize: 12),
              ),
            ),
            ...hits.map(tableTile),
          ]);
        },
      ),
    );
  }
}

// ---- 更新情報 ----

const updateTypeLabel = {0: '新規', 1: '更新', 2: '新規', 3: '更新', 4: '変更'};

class LatestScreen extends StatelessWidget {
  const LatestScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('統計データ更新情報')),
      body: Loader<List<dynamic>>(
        future: data.latest(),
        builder: (context, entries) {
          final items = entries.reversed
              .where((e) => (e['update_type'] as int) < 4)
              .toList();
          if (items.isEmpty) {
            return const Center(
                child: Text('スナップショット取得後の更新はありません。'));
          }
          return ListView(
            children: items
                .map((e) => ListTile(
                      dense: true,
                      title: Text(e['title'] as String),
                      subtitle: Text('公開: ${e['open']}',
                          style: const TextStyle(fontSize: 12)),
                      trailing: Text(updateTypeLabel[e['update_type']] ?? ''),
                      onTap: () => context.push('/latest/${e['id']}'),
                    ))
                .toList(),
          );
        },
      ),
    );
  }
}

class LatestTablesScreen extends StatelessWidget {
  const LatestTablesScreen({super.key, required this.id});

  final String id;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('更新された統計表')),
      body: Loader<List<dynamic>>(
        future: data.latestTables(id),
        builder: (context, rows) {
          final sorted = List<dynamic>.from(rows)
            ..sort((a, b) {
              final c =
                  (a['statics'] as String).compareTo(b['statics'] as String);
              return c != 0
                  ? c
                  : (a['sequence'] as String)
                      .compareTo(b['sequence'] as String);
            });
          return ListView(
            children:
                sorted.map((r) => tableTile(r, showStatics: true)).toList(),
          );
        },
      ),
    );
  }
}
