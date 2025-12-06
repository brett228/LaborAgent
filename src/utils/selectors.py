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

