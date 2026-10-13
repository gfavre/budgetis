document.addEventListener('DOMContentLoaded', () => {
  const button = document.getElementById('add-function-category');
  const template = document.getElementById('function-category-empty-row');
  const rows = document.getElementById('function-category-rows');
  const total = document.getElementById('id_categories-TOTAL_FORMS');
  if (!button || !template || !rows || !total) return;

  button.addEventListener('click', () => {
    const index = Number(total.value);
    const row = template.content.cloneNode(true);
    row.querySelectorAll('[name], [id], [for]').forEach((element) => {
      ['name', 'id', 'for'].forEach((attribute) => {
        if (element.hasAttribute(attribute)) {
          element.setAttribute(attribute, element.getAttribute(attribute).replaceAll('__prefix__', index));
        }
      });
    });
    rows.appendChild(row);
    total.value = index + 1;
    rows.lastElementChild.querySelector('input:not([type="hidden"])')?.focus();
  });
});
