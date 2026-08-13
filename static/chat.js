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
function chatMultiChips(wrap, items, continueLabel, onDone, minSelect) {
  minSelect = minSelect || 0;
  var row = document.createElement('div');
  row.className = 'chat-options';
  var selected = [];

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
        selected.push(item);
        b.classList.add('selected');
      }
      contBtn.disabled = selected.length < minSelect;
    });
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
