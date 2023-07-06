from typing import List
from lambda_labs import LambdaAPI, OfferedInstanceType
import copy


def sorted_by_price_descending(
    instances: List[OfferedInstanceType],
) -> List[OfferedInstanceType]:
    return list(
        sorted(
            instances,
            key=lambda offer: offer.instance_type.price_cents_per_hour,
            reverse=True,
        )
    )


def prompt_user_for_instance_type(api: LambdaAPI) -> OfferedInstanceType:
    valid_offers = []
    unavailable_count = 0

    offers = sorted_by_price_descending(api.get_offered_instance_types())

    for offer in offers:
        description = offer.instance_type.description
        if "A100" not in description and "H100" not in description:
            continue
        cost = int(offer.instance_type.price_cents_per_hour)
        vcpus = offer.instance_type.specs.vcpus
        ram_gib = offer.instance_type.specs.memory_gib
        available_regions = [
            region.name for region in offer.regions_with_capacity_available
        ]
        if not available_regions:
            unavailable_count += 1
            continue
        region_list = ", ".join(available_regions)
        index = len(valid_offers)
        optimal_region = None
        for region in available_regions:
            if region.startswith("us"):
                optimal_region = region
        if optimal_region is None:
            unavailable_count += 1
            continue
        offer_with_optimal_region = copy.deepcopy(offer)
        offer_with_optimal_region.regions_with_capacity_available = [
            region
            for region in offer.regions_with_capacity_available
            if region.name == optimal_region
        ]
        valid_offers.append(offer_with_optimal_region)
        print(
            f"{index + 1}. ${cost / 100:.2f} / hour: {description} ({vcpus} vcpus, {ram_gib} GiB RAM) available in {region_list}"
        )

    if len(valid_offers) == 0:
        raise Exception("No instance types are available in any region.")

    if unavailable_count:
        print(
            f"\n{unavailable_count} instance types are unavailable because there's no capacity. Please select from the remaining options.\n"
        )

    user_choice = int(input("Select an instance type: "))
    return valid_offers[user_choice - 1]
