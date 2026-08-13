// நூலக பணி - chatbot பாணி UI உதவி செயல்பாடுகள்.
// bot/user bubbles மற்றும் chip-தேர்வுகளை உருவாக்கும் பொதுவான helpers.

function chatBot(wrap, text) {
  var d = document.createElement('div');
  d.className = 'chat-bubble chat-bot';
  d.textContent = text;
  wrap.appendChild(d);
  wrap.scrollTop = wrap.scrollHeight;
  return d;
}

function chatUser(wrap, text) {
  var d = document.createElement('div');
  d.className = 'chat-bubble chat-user';
  d.textContent = text;
  wrap.appendChild(d);
  wrap.scrollTop = wrap.scrollHeight;
  return d;
}

// ஒரே தேர்வு (single-select) chips: ஒரு chip-ஐ தேர்வு செய்தவுடன் onPick(item) அழைக்கப்படும்.
function chatChips(wrap, items, onPick) {
  var row = document.createElement('div');
  row.className = 'chat-options';
  items.forEach(function (item) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = item.label;
    b.addEventListener('click', function () {
      row.remove();
      onPick(item);
    });
    row.appendChild(b);
  });
  wrap.appendChild(row);
  wrap.scrollTop = wrap.scrollHeight;
  return row;
}

// பல தேர்வு (multi-select) chips + "தொடர்க" பட்டன். minSelect தேர்வுகள் ஆனதும் பட்டன் இயங்கும்.
// exclusiveValues (optional): இதில் உள்ள value-கள் "தனித்தேர்வு" — இவற்றில் ஒன்றைத்
// தேர்ந்தெடுத்தால் மற்ற அனைத்தும் (exclusive/non-exclusive) தானாக நீக்கப்படும்;
// exclusive அல்லாத ஒன்றைத் தேர்ந்தெடுத்தால், ஏற்கனவே தேர்வான exclusive value-கள்
// தானாக நீக்கப்படும் (எ.கா. "விடுப்பு" vs "ஆய்வு/பார்வை/அலுவலகப் பணி").
function chatMultiChips(wrap, items, continueLabel, onDone, minSelect, exclusiveValues) {
  minSelect = minSelect || 0;
  exclusiveValues = exclusiveValues || [];
  var row = document.createElement('div');
  row.className = 'chat-options';
  var selected = [];
  var entries = [];

  function isExclusive(item) {
    return exclusiveValues.indexOf(item.value) !== -1;
  }

  function refreshUI() {
    entries.forEach(function (entry) {
      entry.btn.classList.toggle('selected', selected.indexOf(entry.item) >= 0);
    });
    contBtn.disabled = selected.length < minSelect;
  }

  items.forEach(function (item) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = item.label;
    b.addEventListener('click', function () {
      var idx = selected.indexOf(item);
      if (idx >= 0) {
        selected.splice(idx, 1);
      } else if (isExclusive(item)) {
        selected = [item];
      } else {
        selected = selected.filter(function (s) { return !isExclusive(s); });
        selected.push(item);
      }
      refreshUI();
    });
    entries.push({ item: item, btn: b });
    row.appendChild(b);
  });

  var contBtn = document.createElement('button');
  contBtn.type = 'button';
  contBtn.className = 'chip chat-continue-btn';
  contBtn.textContent = continueLabel;
  contBtn.disabled = minSelect > 0;
  contBtn.addEventListener('click', function () {
    row.remove();
    onDone(selected);
  });
  row.appendChild(contBtn);

  wrap.appendChild(row);
  wrap.scrollTop = wrap.scrollHeight;
  return row;
}

// தேடல் பெட்டியுடன் கூடிய பல-தேர்வு chip பட்டியல் (எ.கா. நூலகங்கள்). max வரம்பு வரை தேர்வு செய்யலாம்.
function chatSearchChips(wrap, items, max, continueLabel, onDone) {
  var box = document.createElement('div');
  box.className = 'chat-options chat-search-box';

  var search = document.createElement('input');
  search.type = 'text';
  search.className = 'chat-search';
  search.placeholder = 'தேடவும்...';
  box.appendChild(search);

  var list = document.createElement('div');
  list.className = 'chat-chip-list';
  box.appendChild(list);

  var countP = document.createElement('p');
  countP.className = 'lib-count';
  box.appendChild(countP);

  var selected = [];
  var chipButtons = [];

  function updateCount() {
    countP.textContent = selected.length + ' / ' + max + ' தேர்வு செய்யப்பட்டது';
    chipButtons.forEach(function (b) {
      if (!b.classList.contains('selected')) {
        b.disabled = selected.length >= max;
      }
    });
    contBtn.disabled = selected.length === 0;
  }

  items.forEach(function (item) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = item.label;
    b.addEventListener('click', function () {
      var idx = selected.indexOf(item);
      if (idx >= 0) {
        selected.splice(idx, 1);
        b.classList.remove('selected');
      } else {
        if (selected.length >= max) return;
        selected.push(item);
        b.classList.add('selected');
      }
      updateCount();
    });
    chipButtons.push(b);
    list.appendChild(b);
  });

  search.addEventListener('input', function () {
    var q = search.value.trim();
    chipButtons.forEach(function (b, i) {
      b.style.display = items[i].label.indexOf(q) !== -1 ? '' : 'none';
    });
  });

  var contBtn = document.createElement('button');
  contBtn.type = 'button';
  contBtn.className = 'chip chat-continue-btn';
  contBtn.textContent = continueLabel;
  contBtn.disabled = true;
  contBtn.addEventListener('click', function () {
    box.remove();
    onDone(selected);
  });
  box.appendChild(contBtn);

  wrap.appendChild(box);
  wrap.scrollTop = wrap.scrollHeight;
  updateCount();
  return box;
}
