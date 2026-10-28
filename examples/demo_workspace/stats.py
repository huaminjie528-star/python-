"""Small statistics module used by the offline acceptance scenario."""


def mean(nums):
    if not nums:
        return 0
    return sum(nums) / len(nums)
