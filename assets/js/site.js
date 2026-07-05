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
})();
