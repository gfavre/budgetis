/* Project specific Javascript goes here. */

document.body.addEventListener("closeAccountCommentsModal", function () {
  bootstrap.Modal.getInstance(document.getElementById("accountCommentsModal"))?.hide();
});

document.body.addEventListener("closeSankeyRuleModal", function () {
  bootstrap.Modal.getInstance(document.getElementById("sankeyRuleModal"))?.hide();
});

const MODAL_FIELD_SELECTOR = [
  'input:not([type="hidden"]):not([type="button"]):not([type="submit"]):not([type="reset"]):not([type="image"])',
  "textarea",
  "select",
  '[contenteditable="true"]',
].join(", ");

function canFocusModalField(field) {
  return field.matches(MODAL_FIELD_SELECTOR)
    && !field.matches(':disabled, [readonly], [tabindex="-1"]')
    && field.getClientRects().length > 0
    && window.getComputedStyle(field).visibility === "visible";
}

function focusModalField(event) {
  if (!(event.target instanceof Element)) return;
  const modal = event.target.closest(".modal.show");
  if (!modal) return;

  // An unrelated update inside the modal must not interrupt ongoing typing.
  const active = document.activeElement;
  if (modal.contains(active) && canFocusModalField(active)) return;

  const fields = Array.from(modal.querySelectorAll(MODAL_FIELD_SELECTOR)).filter(canFocusModalField);
  const field = fields.find(element => element.hasAttribute("autofocus")) || fields[0];
  field?.focus({preventScroll: true});
}

// Forms can arrive before or after Bootstrap finishes opening the modal.
document.body.addEventListener("shown.bs.modal", focusModalField);
document.body.addEventListener("htmx:afterSwap", focusModalField);
document.body.addEventListener("htmx:afterSettle", focusModalField);
