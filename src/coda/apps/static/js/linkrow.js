let linkTable = null;
let slots = null;

window.addEventListener('DOMContentLoaded', () => {
  linkTable = document.getElementById('linktable');
  slots = linkTable.querySelector('template');
});

function addRow() {
  const templateClone = slots.content.cloneNode(true);
  const row = templateClone.querySelector('tr');
  addRemoveRowButton(row);
  linkTable.append(row);
}

function addRemoveRowButton(row) {
  const td = document.createElement('td');
  td.appendChild(removeRowButton(row));
  row.appendChild(td);
}

function removeRowButton(row) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Remove';
  button.addEventListener('click', removeRow.bind(null, button));
  return button;
}

function removeRow(button) {
  const row = button.parentNode.parentNode;
  linkTable.removeChild(row);
}
