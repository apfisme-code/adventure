import random
import os
import glob
import yaml
import re
from typing import List, Optional, Dict, Any, Tuple, Set, Union

# ------------------- Загрузка конфигурации статусов -------------------

def load_statuses_config(filepath: str = "statuses.yaml") -> Dict[str, Dict]:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("statuses", {})

# ------------------- Загрузка квестов -------------------

class Condition:
    def __init__(self, status: str, operator: str, value: Union[int, bool]):
        self.status = status
        self.operator = operator
        self.value = value

    def check(self, player_statuses: Dict[str, Union[int, bool]]) -> bool:
        current = player_statuses.get(self.status)
        if current is None:
            return False
        if self.operator == "==":
            return current == self.value
        elif self.operator == "!=":
            return current != self.value
        elif self.operator == ">=":
            return current >= self.value
        elif self.operator == "<=":
            return current <= self.value
        elif self.operator == ">":
            return current > self.value
        elif self.operator == "<":
            return current < self.value
        else:
            return False

    @staticmethod
    def parse(condition_dict: Dict[str, str]) -> 'Condition':
        for status, expr in condition_dict.items():
            op_match = re.match(r'([><=!]+)(.+)', expr)
            if op_match:
                operator, raw_value = op_match.groups()
                if raw_value.lower() == 'true':
                    value = True
                elif raw_value.lower() == 'false':
                    value = False
                else:
                    try:
                        value = int(raw_value)
                    except ValueError:
                        raise ValueError(f"Некорректное значение условия: {expr}")
                return Condition(status, operator, value)
        raise ValueError(f"Некорректное условие: {condition_dict}")

    def __repr__(self):
        return f"{self.status} {self.operator} {self.value}"

class Quest:
    def __init__(self, quest_id: str, name: str, description: str, condition: Condition):
        self.id = quest_id
        self.name = name
        self.description = description
        self.condition = condition

    def is_completed(self, player_statuses: Dict[str, Union[int, bool]]) -> bool:
        return self.condition.check(player_statuses)

def load_quests(quests_dir: str = "quests") -> Dict[str, Quest]:
    """Загружает все квесты из YAML-файлов и возвращает словарь id -> Quest."""
    quests = {}
    pattern = os.path.join(quests_dir, "*.yaml")
    yaml_files = glob.glob(pattern) + glob.glob(os.path.join(quests_dir, "*.yml"))
    for filepath in yaml_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data:
                    continue
                quest_id = data.get("id")
                if not quest_id:
                    print(f"Пропущен файл {filepath}: отсутствует id")
                    continue
                name = data.get("name", quest_id)
                description = data.get("description", "")
                raw_condition = data.get("condition", {})
                condition = Condition.parse(raw_condition)  # один словарь
                quests[quest_id] = Quest(quest_id, name, description, condition)
        except Exception as e:
            print(f"Ошибка при загрузке квеста {filepath}: {e}")
    return quests

# ------------------- Модели данных -------------------

class City:
    def __init__(self, name: str, tag: str):
        self.name = name
        self.tag = tag
        self.neighbors: List['City'] = []

    def add_neighbor(self, other: 'City'):
        if other not in self.neighbors:
            self.neighbors.append(other)

    def __repr__(self):
        return self.name


class Outcome:
    def __init__(self, text: str, success_level: str, status_changes: Optional[Dict[str, Union[int, bool]]] = None,
                 add_quest: Optional[str] = None):
        self.text = text
        self.success_level = success_level
        self.status_changes = status_changes or {}
        self.add_quest = add_quest   # id квеста, который добавляется в стек


class Choice:
    def __init__(self, text: str, outcomes: List[Outcome], requires: Optional[List[Condition]] = None):
        self.text = text
        self.outcomes = outcomes
        self.requires = requires or []

    def resolve(self) -> Outcome:
        return random.choice(self.outcomes)


class Event:
    def __init__(self, text: str, choices: List[Choice], tags: List[str],
                 is_goal_event: bool = False, requires: Optional[List[Condition]] = None):
        self.text = text
        self.choices = choices
        self.tags = tags
        self.is_goal_event = is_goal_event
        self.requires = requires or []

    def matches_place(self, place_tags: Set[str]) -> bool:
        return all(tag in place_tags for tag in self.tags)


# ------------------- Загрузчик событий из файлов -------------------

class EventLoader:
    def __init__(self, events_dir: str = "events"):
        self.events_dir = events_dir
        self._tag_cache: Dict[str, List[Event]] = {}
        self._load_all()

    def _load_all(self):
        pattern = os.path.join(self.events_dir, "*.yaml")
        yaml_files = glob.glob(pattern) + glob.glob(os.path.join(self.events_dir, "*.yml"))
        for filepath in yaml_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    tags = data.get("tags", [])
                    event = self._parse_event(data)
                    if event:
                        for tag in tags:
                            self._tag_cache.setdefault(tag, []).append(event)
            except Exception as e:
                print(f"Ошибка при загрузке файла {filepath}: {e}")

    def _parse_event(self, data: Dict[str, Any]) -> Optional[Event]:
        try:
            text = data["text"]
            is_goal = data.get("is_goal_event", False)
            tags = data.get("tags", [])
            requires = self._parse_conditions(data.get("requires", []))
            choices_data = data.get("choices", [])
            choices = []
            for choice_item in choices_data:
                choice_text = choice_item["text"]
                choice_requires = self._parse_conditions(choice_item.get("requires", []))
                outcomes_data = choice_item.get("outcomes", [])
                outcomes = []
                for out in outcomes_data:
                    level = out["success_level"]
                    changes = out.get("status_changes", {})
                    add_quest = out.get("add_quest")  # может быть строка
                    outcomes.append(Outcome(out["text"], level, changes, add_quest))
                choices.append(Choice(choice_text, outcomes, choice_requires))
            return Event(text, choices, tags, is_goal, requires)
        except KeyError as e:
            print(f"Ошибка в данных события: отсутствует поле {e}")
            return None

    def _parse_conditions(self, raw_conditions: List[Dict[str, str]]) -> List[Condition]:
        conditions = []
        for cond_dict in raw_conditions:
            conditions.append(Condition.parse(cond_dict))
        return conditions

    def get_events_by_tag(self, tag: str) -> List[Event]:
        return self._tag_cache.get(tag, [])


# ------------------- Игровой движок -------------------

class Player:
    def __init__(self, start_city: City, quest_stack: List[Quest], statuses_config: Dict[str, Dict]):
        self.current_city = start_city
        self.quest_stack = quest_stack  # стек квестов, последний – текущий
        self.statuses_config = statuses_config
        self.statuses = {}
        for name, info in statuses_config.items():
            if info["type"] == "numeric":
                self.statuses[name] = info.get("default", 0)
            elif info["type"] == "boolean":
                self.statuses[name] = info.get("default", False)
        self.history: List[Dict] = []
        self.game_over = False

    def move_to(self, city: City):
        self.current_city = city
        self.history.append({"action": "move", "to": city.name})

    def add_event_record(self, event_type: str, event: Event, choice: Choice,
                         outcome: Outcome, status_changes: Optional[Dict[str, Union[int, bool]]] = None,
                         added_quest: Optional[str] = None):
        self.history.append({
            "type": event_type,
            "event": event.text,
            "choice": choice.text,
            "outcome": outcome.text,
            "success_level": outcome.success_level,
            "status_changes": status_changes or {},
            "added_quest": added_quest
        })

    def apply_status_changes(self, changes: Dict[str, Union[int, bool]]):
        for status, value in changes.items():
            if status not in self.statuses_config:
                continue
            info = self.statuses_config[status]
            if info["type"] == "numeric":
                if not isinstance(value, int):
                    continue
                current = self.statuses.get(status, 0)
                new_value = current + value
                min_val = info.get("min", 0)
                max_val = info.get("max", 10)
                if new_value < min_val:
                    new_value = min_val
                if new_value > max_val:
                    new_value = max_val
                self.statuses[status] = new_value
            elif info["type"] == "boolean":
                if not isinstance(value, bool):
                    continue
                self.statuses[status] = value

    def has_conditions(self, conditions: List[Condition]) -> bool:
        return all(cond.check(self.statuses) for cond in conditions)

    def add_quest(self, quest: Quest):
        """Добавляет квест в стек (становится текущим)."""
        self.quest_stack.append(quest)

    def get_current_quest(self) -> Optional[Quest]:
        """Возвращает текущий (последний) квест или None, если стек пуст."""
        if self.quest_stack:
            return self.quest_stack[-1]
        return None

    def check_current_quest(self) -> bool:
        """Проверяет, выполнен ли текущий квест. Если да, удаляет его и возвращает True."""
        current = self.get_current_quest()
        if current and current.is_completed(self.statuses):
            self.quest_stack.pop()
            return True
        return False

    def check_all_quests_done(self) -> bool:
        """Проверяет, пуст ли стек квестов (все выполнены)."""
        return len(self.quest_stack) == 0


class Game:
    def __init__(self, loader: EventLoader, statuses_config: Dict[str, Dict], quests: Dict[str, Quest]):
        self.loader = loader
        self.statuses_config = statuses_config
        self.all_quests = quests
        self.cities, self.edge_tags = self._build_map()
        self.player = None
        self.current_edge_tag = None

    def _build_map(self) -> Tuple[Dict[str, City], Dict[Tuple[str, str], str]]:
        city_tags = ['деревня', 'деревня', 'деревня', 'небольшой город', 'небольшой город', 'столица', 'столица']
        random.shuffle(city_tags)
        cities = {name: City(name, tag) for name, tag in zip(['A', 'B', 'C', 'D', 'E', 'F', 'G'], city_tags)}

        edges = [
            ('A', 'B'), ('A', 'C'), ('A', 'D'),
            ('B', 'C'), ('B', 'E'), ('B', 'F'),
            ('C', 'D'), ('C', 'G'),
            ('D', 'E'), ('D', 'F'),
            ('E', 'F'), ('E', 'G'),
            ('F', 'G')
        ]
        terrain_tags = ['лес', 'болото', 'море', 'джунгли', 'пустыня', 'горы']
        edge_tags = {}
        for u, v in edges:
            tag = random.choice(terrain_tags)
            key = tuple(sorted((u, v)))
            edge_tags[key] = tag
            cities[u].add_neighbor(cities[v])
            cities[v].add_neighbor(cities[u])

        return cities, edge_tags

    def get_edge_tag(self, city1: City, city2: City) -> Optional[str]:
        key = tuple(sorted((city1.name, city2.name)))
        return self.edge_tags.get(key)

    def get_available_events(self, events: List[Event]) -> List[Event]:
        return [ev for ev in events if self.player.has_conditions(ev.requires)]

    def get_available_choices(self, choices: List[Choice]) -> List[Choice]:
        return [ch for ch in choices if self.player.has_conditions(ch.requires)]

    def print_statuses(self, prefix: str = "Текущие статусы"):
        if self.player.statuses:
            parts = []
            for name, value in sorted(self.player.statuses.items()):
                if isinstance(value, bool):
                    parts.append(f"{name}: {'да' if value else 'нет'}")
                else:
                    parts.append(f"{name}: {value}")
            print(f"{prefix}: {', '.join(parts)}")
        else:
            print(f"{prefix}: нет")

    def start(self):
        # Выбор начального квеста случайным образом (из загруженных)
        initial_quests = ['initial_wealth', 'initial_fame', 'initial_wise', 'initial_fencing', 'initial_thief']
        available_initial = [qid for qid in initial_quests if qid in self.all_quests]
        if not available_initial:
            print("Нет начальных квестов! Проверьте папку quests.")
            return
        chosen_id = random.choice(available_initial)
        initial_quest = self.all_quests[chosen_id]

        start_city = random.choice(list(self.cities.values()))
        self.player = Player(start_city, [initial_quest], self.statuses_config)
        self.current_edge_tag = None

        print(f"Добро пожаловать в игру-путешествие по сказочному миру!")
        print(f"Вы начинаете в городе {start_city.name} (тип: {start_city.tag}).")
        print(f"Ваш первый квест: {initial_quest.name} - {initial_quest.description}")
        print("Путешествуйте, выполняйте квесты и создавайте свою историю!\n")

        self.city_events = self.loader.get_events_by_tag("city")
        self.travel_events = self.loader.get_events_by_tag("travel")

        while not self.player.game_over:
            self.show_status()
            self.handle_move()
            if self.player.game_over:
                break
            if random.random() < 0.3 and self.travel_events:
                self.handle_travel_event()
                if self.player.game_over:
                    break
            if self.city_events:
                self.handle_city_event()
                if self.player.game_over:
                    break
            else:
                print("Нет доступных городских событий. Игра завершена.")
                self.player.game_over = True

        print("\n=== Игра завершена ===")
        if self.player.check_all_quests_done():
            print("Поздравляем! Вы выполнили все квесты и завершили игру!")
        else:
            print("Игра прервана. Вы не выполнили все квесты.")
        self.print_statuses("Финальные статусы")
        print("Ваш путь:")
        for record in self.player.history:
            if record.get("action") == "move":
                print(f"  Переход в {record['to']}")
            else:
                print(f"  {record['type']}: {record['event']}")
                print(f"    Выбор: {record['choice']} -> {record['outcome']} ({record['success_level']})")
                if record.get("status_changes"):
                    for stat, delta in record["status_changes"].items():
                        if isinstance(delta, bool):
                            print(f"    {stat}: {'установлен' if delta else 'сброшен'}")
                        else:
                            print(f"    {stat}: {delta:+d}")
                if record.get("added_quest"):
                    q = self.all_quests.get(record["added_quest"])
                    if q:
                        print(f"    Добавлен квест: {q.name}")

    def show_status(self):
        current_quest = self.player.get_current_quest()
        quest_str = f"{current_quest.name} ({current_quest.condition})" if current_quest else "Нет активного квеста"
        print(f"\n--- Текущий город: {self.player.current_city.name} (тип: {self.player.current_city.tag}) ---")
        print(f"Текущий квест: {quest_str}")
        print(f"Осталось квестов: {len(self.player.quest_stack)}")
        self.print_statuses()
        neighbors = self.player.current_city.neighbors
        print("Доступные направления:")
        for i, city in enumerate(neighbors):
            edge_tag = self.get_edge_tag(self.player.current_city, city)
            print(f"  {i+1}. {city.name} ({city.tag}) - путь через {edge_tag}")

    def handle_move(self):
        neighbors = self.player.current_city.neighbors
        while True:
            try:
                choice = int(input("Выберите номер города для перехода: "))
                if 1 <= choice <= len(neighbors):
                    target = neighbors[choice-1]
                    self.current_edge_tag = self.get_edge_tag(self.player.current_city, target)
                    self.player.move_to(target)
                    print(f"\nВы перешли в {target.name}.")
                    # Проверяем выполнение текущего квеста после перемещения
                    self.check_and_update_quests()
                    self.print_statuses("Ваши статусы после перемещения")
                    break
                else:
                    print("Неверный номер. Попробуйте снова.")
            except ValueError:
                print("Введите число.")

    def handle_travel_event(self):
        if self.current_edge_tag is None:
            return
        place_tags = {"travel", self.current_edge_tag}
        candidates = [ev for ev in self.travel_events if ev.matches_place(place_tags)]
        available = self.get_available_events(candidates)
        if not available:
            print(f"Нет подходящих событий в пути через {self.current_edge_tag}.")
            return
        event = random.choice(available)
        print(f"\n[В пути через {self.current_edge_tag}] {event.text}")
        self.process_event(event, "travel")

    def handle_city_event(self):
        place_tags = {"city", self.player.current_city.tag}
        candidates = [ev for ev in self.city_events if ev.matches_place(place_tags)]
        available = self.get_available_events(candidates)
        if not available:
            print(f"Нет подходящих событий в городе {self.player.current_city.name}.")
            return
        event = random.choice(available)
        print(f"\n[Город {self.player.current_city.name} ({self.player.current_city.tag})] {event.text}")
        self.process_event(event, "city")

    def process_event(self, event: Event, event_type: str):
        available_choices = self.get_available_choices(event.choices)
        if not available_choices:
            print("Нет доступных вариантов для ваших статусов. Событие пропущено.")
            return

        for i, choice in enumerate(available_choices):
            req_str = f" (требуется: {', '.join(str(c) for c in choice.requires)})" if choice.requires else ""
            print(f"  {i+1}. {choice.text}{req_str}")

        while True:
            try:
                idx = int(input("Ваш выбор (номер): ")) - 1
                if 0 <= idx < len(available_choices):
                    chosen_choice = available_choices[idx]
                    break
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Введите число.")

        outcome = chosen_choice.resolve()
        print(f"Результат: {outcome.text}")

        # Применяем изменения статусов
        if outcome.status_changes:
            old_values = {s: self.player.statuses.get(s) for s in outcome.status_changes.keys()}
            self.player.apply_status_changes(outcome.status_changes)
            for status, delta in outcome.status_changes.items():
                new_val = self.player.statuses.get(status)
                old_val = old_values.get(status)
                if isinstance(delta, bool):
                    print(f"{status}: {'да' if new_val else 'нет'} (было: {'да' if old_val else 'нет'})")
                else:
                    print(f"{status}: {old_val} → {new_val} ({delta:+d})")

        # Добавление квеста
        added_quest_id = None
        if outcome.add_quest:
            quest = self.all_quests.get(outcome.add_quest)
            if quest:
                self.player.add_quest(quest)
                added_quest_id = outcome.add_quest
                print(f"Новый квест добавлен в стек: {quest.name}")
            else:
                print(f"Квест с id '{outcome.add_quest}' не найден!")

        # Проверка выполнения текущего квеста
        self.check_and_update_quests()

        self.print_statuses("Обновлённые статусы")

        self.player.add_event_record(event_type, event, chosen_choice, outcome,
                                     outcome.status_changes, added_quest_id)

        if self.player.check_all_quests_done():
            print("Поздравляем! Вы выполнили все квесты и завершили игру!")
            self.player.game_over = True

    def check_and_update_quests(self):
        """Проверяет, выполнен ли текущий квест, и если да, удаляет его (переходит к предыдущему)."""
        while not self.player.check_all_quests_done():
            if self.player.check_current_quest():
                current = self.player.get_current_quest()
                if current:
                    print(f"Квест '{current.name}' выполнен! Переход к предыдущему квесту.")
                # После удаления, проверяем следующий
            else:
                break  # текущий не выполнен, выходим


# ------------------- Запуск -------------------

if __name__ == "__main__":
    statuses_config = load_statuses_config("statuses.yaml")
    quests = load_quests("quests")
    loader = EventLoader("events")
    game = Game(loader, statuses_config, quests)
    game.start()