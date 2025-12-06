def prompt_user_choice(options):
    print("\n선택지를 골라주세요:")
    for i, o in enumerate(options, 1):
        print(f"{i}. {o}")

    while True:
        try:
            idx = int(input("> "))
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except:
            pass
        print("번호가 잘못되었습니다. 다시 입력해주세요.")


def prompt_user_choice_multiple(options):
    print("\n선택지를 골라주세요 (여러 개 선택 가능, 쉼표로 구분):")
    for i, o in enumerate(options, 1):
        print(f"{i}. {o}")

    while True:
        user_input = input("> ")
        try:
            # 쉼표, 공백 구분으로 나누고 숫자로 변환
            indices = [int(x.strip()) for x in user_input.replace(" ", "").split(",")]
            if all(1 <= idx <= len(options) for idx in indices):
                # 선택된 옵션 리스트 반환
                return [options[idx - 1] for idx in indices]
        except:
            pass
        print("입력이 잘못되었습니다. 올바른 번호를 쉼표로 구분하여 입력해주세요.")
