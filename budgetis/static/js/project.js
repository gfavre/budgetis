/* Project specific Javascript goes here. */

document.body.addEventListener("closeAccountCommentsModal", function () {
  bootstrap.Modal.getInstance(document.getElementById("accountCommentsModal"))?.hide();
});
