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
                        raise ValueError(f"Некорректное значение: {expr}")
                return Condition(status, operator, value)
        raise ValueError(f"Некорректное условие: {condition_dict}")

    def __repr__(self):
        return f"{self.status} {self.operator} {self.value}"


class Outcome:
    def __init__(self, text: str, success_level: str, status_changes: Optional[Dict[str, Union[int, bool]]] = None,
                 quest_add: Optional[str] = None):
        self.text = text
        self.success_level = success_level
        self.status_changes = status_changes or {}
        self.quest_add = quest_add  # id квеста, который добавляется в стек


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


# ------------------- Загрузчик событий -------------------

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
                    quest_add = out.get("quest_add")  # может быть строка (id квеста)
                    outcomes.append(Outcome(out["text"], level, changes, quest_add))
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


# ------------------- Загрузчик квестов -------------------

class Quest:
    def __init__(self, quest_id: str, title: str, description: str,
                 condition: Condition, on_complete: Dict[str, Union[int, bool]] = None,
                 is_initial: bool = False):
        self.id = quest_id
        self.title = title
        self.description = description
        self.condition = condition
        self.on_complete = on_complete or {}
        self.is_initial = is_initial

    def is_completed(self, player_statuses: Dict[str, Union[int, bool]]) -> bool:
        return self.condition.check(player_statuses)

    def apply_completion(self, player):
        """Применяет изменения статусов при завершении квеста."""
        if self.on_complete:
            player.apply_status_changes(self.on_complete)


class QuestLoader:
    def __init__(self, quests_dir: str = "quests"):
        self.quests_dir = quests_dir
        self._quests: Dict[str, Quest] = {}
        self._load_all()

    def _load_all(self):
        pattern = os.path.join(self.quests_dir, "*.yaml")
        yaml_files = glob.glob(pattern) + glob.glob(os.path.join(self.quests_dir, "*.yml"))
        for filepath in yaml_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    quest = self._parse_quest(data)
                    if quest:
                        self._quests[quest.id] = quest
            except Exception as e:
                print(f"Ошибка при загрузке квеста {filepath}: {e}")

    def _parse_quest(self, data: Dict[str, Any]) -> Optional[Quest]:
        try:
            qid = data["id"]
            title = data["title"]
            description = data["description"]
            condition_dict = data["condition"]
            condition = Condition.parse(condition_dict)
            on_complete = data.get("on_complete", {})
            is_initial = data.get("is_initial", False)
            return Quest(qid, title, description, condition, on_complete, is_initial)
        except KeyError as e:
            print(f"Ошибка в данных квеста: отсутствует поле {e}")
            return None

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        return self._quests.get(quest_id)

    def get_initial_quest(self) -> Optional[Quest]:
        for q in self._quests.values():
            if q.is_initial:
                return q
        return None


# ------------------- Игровой движок -------------------

class Player:
    def __init__(self, start_city: City, quest_stack: List[Quest], statuses_config: Dict[str, Dict]):
        self.current_city = start_city
        self.statuses_config = statuses_config
        self.statuses = {}
        for name, info in statuses_config.items():
            if info["type"] == "numeric":
                self.statuses[name] = info.get("default", 0)
            elif info["type"] == "boolean":
                self.statuses[name] = info.get("default", False)
        self.quest_stack = quest_stack.copy()  # список квестов (последний – текущий)
        self.history: List[Dict] = []
        self.game_over = False

    def move_to(self, city: City):
        self.current_city = city
        self.history.append({"action": "move", "to": city.name})

    def add_event_record(self, event_type: str, event: Event, choice: Choice,
                         outcome: Outcome, status_changes: Optional[Dict[str, Union[int, bool]]] = None,
                         quest_added: Optional[str] = None):
        self.history.append({
            "type": event_type,
            "event": event.text,
            "choice": choice.text,
            "outcome": outcome.text,
            "success_level": outcome.success_level,
            "status_changes": status_changes or {},
            "quest_added": quest_added
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

    def get_current_quest(self) -> Optional[Quest]:
        if self.quest_stack:
            return self.quest_stack[-1]
        return None

    def check_current_quest_completed(self) -> bool:
        current = self.get_current_quest()
        if current:
            return current.is_completed(self.statuses)
        return False

    def complete_current_quest(self):
        current = self.get_current_quest()
        if current:
            current.apply_completion(self)
            self.quest_stack.pop()
            if not self.quest_stack:
                self.game_over = True  # все квесты выполнены!

    def add_quest(self, quest: Quest):
        self.quest_stack.append(quest)

    def has_quest(self, quest_id: str) -> bool:
        return any(q.id == quest_id for q in self.quest_stack)


class Game:
    def __init__(self, event_loader: EventLoader, quest_loader: QuestLoader,
                 statuses_config: Dict[str, Dict]):
        self.event_loader = event_loader
        self.quest_loader = quest_loader
        self.statuses_config = statuses_config
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

    def print_quests(self):
        if self.player.quest_stack:
            print("Текущие квесты (стек):")
            for i, q in enumerate(self.player.quest_stack):
                marker = " (текущий)" if i == len(self.player.quest_stack)-1 else ""
                print(f"  {i+1}. {q.title}{marker}")
                print(f"     {q.description}")
        else:
            print("Нет активных квестов.")

    def start(self):
        # Получаем начальный квест
        initial_quest = self.quest_loader.get_initial_quest()
        if not initial_quest:
            print("Ошибка: не найден начальный квест. Убедитесь, что в папке quests есть квест с is_initial: true")
            return

        start_city = random.choice(list(self.cities.values()))
        self.player = Player(start_city, [initial_quest], self.statuses_config)
        self.current_edge_tag = None

        print(f"Добро пожаловать в игру-путешествие по сказочному миру!")
        print(f"Вы начинаете в городе {start_city.name} (тип: {start_city.tag}).")
        print("Ваша цель: выполнить все квесты в стеке.")
        print("Текущий квест (первый):")
        print(f"  {initial_quest.title}: {initial_quest.description}")
        print("Путешествуйте, делайте выборы, развивайте свои навыки и завершайте квесты!\n")

        self.city_events = self.event_loader.get_events_by_tag("city")
        self.travel_events = self.event_loader.get_events_by_tag("travel")

        if not self.city_events:
            print("ВНИМАНИЕ: Не найдено городских событий (тег 'city'). Проверьте папку events.")
        if not self.travel_events:
            print("ВНИМАНИЕ: Не найдено событий в пути (тег 'travel'). Проверьте папку events.")

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
        if not self.player.quest_stack:
            print("Поздравляем! Вы выполнили все квесты и победили!")
        else:
            print("Игра прервана. У вас остались невыполненные квесты.")
        self.print_statuses("Финальные статусы")
        print("Ваш путь:")
        for record in self.player.history:
            if record.get("action") == "move":
                print(f"  Переход в {record['to']}")
            else:
                print(f"  {record['type']}: {record['event']}")
                print(f"    Выбор: {record['choice']} -> {record['outcome']} ({record['success_level']})")
                if record.get("status_changes"):
                    changes = record["status_changes"]
                    for stat, delta in changes.items():
                        if isinstance(delta, bool):
                            print(f"    {stat}: {'установлен' if delta else 'сброшен'}")
                        else:
                            print(f"    {stat}: {delta:+d}")
                if record.get("quest_added"):
                    print(f"    Добавлен квест: {record['quest_added']}")
        print("Оставшиеся квесты:")
        for q in self.player.quest_stack:
            print(f"  {q.title}: {q.description}")

    def show_status(self):
        print(f"\n--- Текущий город: {self.player.current_city.name} (тип: {self.player.current_city.tag}) ---")
        self.print_statuses()
        self.print_quests()
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
                    self.print_statuses("Ваши статусы после перемещения")
                    # Проверяем, не выполнен ли текущий квест после перемещения (статусы могли измениться)
                    self.check_quest_completion()
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
            self.print_statuses("Обновлённые статусы")
        else:
            self.print_statuses("Ваши статусы")

        # Добавление нового квеста
        quest_added = None
        if outcome.quest_add:
            quest = self.quest_loader.get_quest(outcome.quest_add)
            if quest:
                self.player.add_quest(quest)
                quest_added = quest.id
                print(f"Добавлен новый квест: {quest.title}")
                print(f"  {quest.description}")
            else:
                print(f"Ошибка: квест с id '{outcome.quest_add}' не найден.")

        self.player.add_event_record(event_type, event, chosen_choice, outcome,
                                     outcome.status_changes, quest_added)

        # Проверяем выполнение текущего квеста после события
        self.check_quest_completion()

    def check_quest_completion(self):
        """Проверяет, выполнен ли текущий квест, и если да – завершает его."""
        if self.player.game_over:
            return
        while self.player.quest_stack and self.player.check_current_quest_completed():
            current_quest = self.player.get_current_quest()
            print(f"\nКвест выполнен: {current_quest.title}!")
            self.player.complete_current_quest()  # применяет on_complete и удаляет
            if self.player.quest_stack:
                new_current = self.player.get_current_quest()
                print(f"Теперь текущий квест: {new_current.title}")
                print(f"  {new_current.description}")
            else:
                print("Все квесты выполнены! Вы победили!")
                self.player.game_over = True
                break


# ------------------- Запуск -------------------

if __name__ == "__main__":
    statuses_config = load_statuses_config("statuses.yaml")
    event_loader = EventLoader("events")
    quest_loader = QuestLoader("quests")
    game = Game(event_loader, quest_loader, statuses_config)
    game.start()