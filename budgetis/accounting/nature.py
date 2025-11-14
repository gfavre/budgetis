from collections import OrderedDict

from django.utils.translation import gettext_lazy as _


NATURE_GROUPS = OrderedDict(
    [
        (30, _("Authorities and staff")),
        (31, _("Goods, services, merchandise")),
        (32, _("Interest expense")),
        (33, _("Depreciation")),
        (35, _("Reimbursements, contributions, and subsidies to public authorities")),
        (36, _("Aid and subsidies")),
        (38, _("Allocations to special funds and financing")),
        (39, _("Internal allocations")),
        (40, _("Taxes")),
        (41, _("Licenses, concessions")),
        (42, _("Income from assets")),
        (43, _("Taxes, fees, proceeds from sales")),
        (44, _("Shares in cantonal revenues")),
        (45, _("Contributions and reimbursements from public authorities")),
        (46, _("Other benefits and subsidies")),
        (48, _("Withdrawals from special funds and financing")),
        (49, _("Internal allocations")),
    ]
)
