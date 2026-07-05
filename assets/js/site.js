// eCitizenStatic 共通スクリプト (K1: jQuery 廃止後の最小 vanilla JS)
(function () {
    "use strict";

    // モバイルナビ開閉
    var toggle = document.querySelector(".nav-toggle");
    var navArea = document.querySelector(".nav-area");
    if (toggle && navArea) {
        toggle.addEventListener("click", function () {
            var open = navArea.classList.toggle("open");
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        });
    }

    // 県セレクタ: /Population/CityList/{pref}.json を取得してリンクを差し替える
    // (旧 City.cshtml の changePref/linklist の置き換え)
    var pref = document.getElementById("pref");
    var list = document.getElementById("citylinklist");
    if (pref && list) {
        var base = pref.dataset.linkBase || "/Population/City/";
        pref.addEventListener("change", function () {
            fetch("/Population/CityList/" + pref.value + ".json")
                .then(function (r) { return r.json(); })
                .then(function (cities) {
                    list.textContent = "";
                    cities.forEach(function (c) {
                        var li = document.createElement("li");
                        li.className = "chartlink";
                        var a = document.createElement("a");
                        a.href = base + c.code;
                        a.textContent = c.name;
                        li.appendChild(a);
                        list.appendChild(li);
                    });
                });
        });
    }

    // 人口ピラミッド: 14年分の SVG を事前埋め込みしておき、表示/非表示を切り替えるだけ
    // (K8: クライアント側チャートライブラリ・fetch は使わない。旧 CityPyramid.cshtml の
    // changeYear/auto の置き換え)
    var figures = document.querySelectorAll(".pyramid-year");
    var yearSelect = document.getElementById("year");
    if (figures.length && yearSelect) {
        var prevBtn = document.getElementById("pervyear");
        var nextBtn = document.getElementById("nextyear");
        var autoBtn = document.getElementById("auto");
        var autoTimer = null;

        function showYear(year) {
            figures.forEach(function (f) {
                f.hidden = f.dataset.year !== String(year);
            });
        }
        function stopAuto() {
            if (autoTimer) {
                clearInterval(autoTimer);
                autoTimer = null;
                autoBtn.value = "自動動画";
            }
        }
        yearSelect.addEventListener("change", function () {
            stopAuto();
            showYear(this.value);
        });
        if (prevBtn) {
            prevBtn.addEventListener("click", function () {
                stopAuto();
                var i = yearSelect.selectedIndex - 1;
                if (i >= 0) { yearSelect.selectedIndex = i; showYear(yearSelect.value); }
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                stopAuto();
                var i = yearSelect.selectedIndex + 1;
                if (i < yearSelect.options.length) { yearSelect.selectedIndex = i; showYear(yearSelect.value); }
            });
        }
        if (autoBtn) {
            autoBtn.addEventListener("click", function () {
                if (autoTimer) { stopAuto(); return; }
                autoBtn.value = "停止";
                yearSelect.selectedIndex = 0;
                showYear(yearSelect.value);
                autoTimer = setInterval(function () {
                    var i = yearSelect.selectedIndex + 1;
                    if (i >= yearSelect.options.length) { stopAuto(); return; }
                    yearSelect.selectedIndex = i;
                    showYear(yearSelect.value);
                }, 1500);
            });
        }
    }
})();
