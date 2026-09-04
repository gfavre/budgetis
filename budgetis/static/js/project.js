/* Project specific Javascript goes here. */

document.body.addEventListener("closeAccountCommentsModal", function () {
  bootstrap.Modal.getInstance(document.getElementById("accountCommentsModal"))?.hide();
});

document.body.addEventListener("closeSankeyRuleModal", function () {
  bootstrap.Modal.getInstance(document.getElementById("sankeyRuleModal"))?.hide();
});
